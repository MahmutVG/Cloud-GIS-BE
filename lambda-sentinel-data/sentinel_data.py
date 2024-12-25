import json
import os
import logging
import requests
import numpy as np
from osgeo import gdal
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError
from concurrent.futures import ThreadPoolExecutor

load_dotenv()
s3 = boto3.client('s3')
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("MapLocations")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())
gdal.UseExceptions()

def setup_gdal_output(input_dataset, output_path, bands=1, dtype=gdal.GDT_Float32):
    driver = gdal.GetDriverByName("GTiff")
    out_ds = driver.Create(output_path, input_dataset.RasterXSize, input_dataset.RasterYSize, bands, dtype)
    out_ds.SetGeoTransform(input_dataset.GetGeoTransform())
    out_ds.SetProjection(input_dataset.GetProjection())
    return out_ds

def upload_to_s3(file_path, bucket_name, object_name):
    try:
        s3.head_object(Bucket=bucket_name, Key=object_name)
        logger.info(f"'{object_name}' already exists in '{bucket_name}'. Skipping upload.")
    except ClientError:
        try:
            s3.upload_file(file_path, bucket_name, object_name)
            logger.info(f"Uploaded '{object_name}' to '{bucket_name}'.")
        except ClientError as e:
            logger.error(f"Failed to upload '{object_name}' to S3: {e}")

def resample_band(input_path, x_res, y_res):
    output_path = input_path.replace('.tif', '_resampled.tif')
    gdal.Warp(output_path, gdal.Open(input_path), xRes=x_res, yRes=y_res)
    os.remove(input_path)
    return output_path

def generate_bbox(lat, lon, radius):
    return f"{lon - radius},{lat - radius},{lon + radius},{lat + radius}"

def calculate_ndmi(nir_ds, swir_ds, output_path):
    nir_array = nir_ds.ReadAsArray().astype(np.float32)
    swir_array = swir_ds.ReadAsArray().astype(np.float32)
    ndmi = (nir_array - swir_array) / (nir_array + swir_array)
    out_ds = setup_gdal_output(nir_ds, output_path)
    out_ds.GetRasterBand(1).WriteArray(ndmi)
    out_ds = None
    return output_path

def calculate_msavi2(nir_ds, red_ds, output_path):
    nir_array = nir_ds.ReadAsArray().astype(np.float32)
    red_array = red_ds.ReadAsArray().astype(np.float32)
    msavi2 = (2 * nir_array + 1 - np.sqrt((2 * nir_array + 1)**2 - 8 * (nir_array - red_array))) / 2
    out_ds = setup_gdal_output(nir_ds, output_path)
    out_ds.GetRasterBand(1).WriteArray(msavi2)
    out_ds = None
    return output_path

def download_band(band_name, band_url, local_path):
    if not os.path.exists(local_path):
        response = requests.get(band_url)
        with open(local_path, 'wb') as f:
            f.write(response.content)
    return band_name, local_path

def download_sentinel_bands(image, tmp_dir="/tmp"):
    bands = {
        "nir": image["assets"]["nir"]["href"],
        "swir": image["assets"]["swir22"]["href"],
        "red": image["assets"]["red"]["href"],
    }
    local_paths = {}
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(download_band, band_name, band_url, os.path.join(tmp_dir, f"{image['id']}_{band_name}.tif")) for band_name, band_url in bands.items()]
        for future in futures:
            band_name, local_path = future.result()
            local_paths[band_name] = local_path
    return local_paths

def fetch_sentinel_image(date, bbox):
    url = f"https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items?limit=12&datetime={date}&bbox={bbox}"
    response = requests.get(url)
    if response.status_code == 200:
        images = response.json().get("features", [])
        return sorted(images, key=lambda x: x['properties']['eo:cloud_cover'])[0] if images else None

def process_sentinel_image(image, bucket_name):
    bands = download_sentinel_bands(image)
    bands["swir"] = resample_band(bands["swir"], 10, 10)
    nir_ds = gdal.Open(bands["nir"])
    swir_ds = gdal.Open(bands["swir"])
    red_ds = gdal.Open(bands["red"])
    ndmi_output = f"/tmp/{image['id']}_ndmi.tif"
    msavi2_output = f"/tmp/{image['id']}_msavi2.tif"
    calculate_ndmi(nir_ds, swir_ds, ndmi_output)
    calculate_msavi2(nir_ds, red_ds, msavi2_output)
    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(upload_to_s3, ndmi_output, bucket_name, os.path.basename(ndmi_output)),
            executor.submit(upload_to_s3, msavi2_output, bucket_name, os.path.basename(msavi2_output))
        ]
        for future in futures:
            future.result()  # Ensure each upload is completed

def check_http_method(event):
    http_method = event.get('httpMethod')
    if http_method != 'POST':
        logger.warning("Unsupported HTTP method: %s", http_method)
        return {
            'statusCode': 405,
            'message': 'Method not allowed'
        }
    return None

def get_location_data(location_id):
    location_data = table.get_item(Key={"LocationID": location_id}).get("Item")
    if not location_data:
        logger.error(f"Location with ID '{location_id}' not found.")
        return {
            "statusCode": 404,
            "message": "Location not found."
        }
    return location_data

def validate_coordinates(coords):
    bbox = generate_bbox(float(coords["lat"]), float(coords["lon"]), 0.00001)
    x_min, y_min, x_max, y_max = map(float, bbox.split(","))
    if x_min < 32.3960 or x_max > 33.2340 or y_min < 39.8200 or y_max > 40.4060:
        logger.error("Coordinates out of bounds. Must be within Ankara.")
        return {
            "statusCode": 400,
            "message": "Coordinates out of bounds. Must be within Ankara."
        }
    return bbox

def check_existing_images(image_id, bucket_name):
    try:
        ndmi_exists = s3.head_object(Bucket=bucket_name, Key=f"{image_id}_ndmi.tif")
    except ClientError:
        ndmi_exists = None
    try:
        msavi2_exists = s3.head_object(Bucket=bucket_name, Key=f"{image_id}_msavi2.tif")
    except ClientError:
        msavi2_exists = None
    if ndmi_exists and msavi2_exists:
        logger.info(f"Sentinel-2 image '{image_id}' already processed. Skipping.")
        #UPDATE STATUS
        return {
            "statusCode": 200,
            "message": "Image already processed.",
            "ndmi": f"{image_id}_ndmi.tif",
            "msavi2": f"{image_id}_msavi2.tif"
        }
    return None


def handler(event, context):
    logger.info("Event received: %s", json.dumps(event))  # Log the event for debugging

    error_response = check_http_method(event)
    if error_response:
        return error_response

    location_id = event.get('pathParameters', {}).get('uuid', "70eb8165-7319-4b75-9807-df146714ff3a")
    location_data = get_location_data(location_id)

    if isinstance(location_data, dict) and "statusCode" in location_data:
        return location_data

    date = event.get("date", "2024-03-01T00:00:00.000Z/2024-09-01T00:00:00.000Z")
    coords = location_data.get("coordinates")
    bbox = validate_coordinates(coords)
    if isinstance(bbox, dict) and "statusCode" in bbox:
        return bbox

    image = fetch_sentinel_image(date, bbox)
    if image:
        bucket_name = os.getenv("OUTPUT_BUCKET_NAME")
        existing_images_response = check_existing_images(image['id'], bucket_name)
        if existing_images_response:
            return existing_images_response

        location_data["status"] = "PROCESSING"
        table.put_item(Item=location_data)

        process_sentinel_image(image, bucket_name)

        location_data["status"] = "PROCESSED"
        location_data["ndmi"] = f"https://{bucket_name}.s3.amazonaws.com/{image['id']}_ndmi.tif"
        location_data["msavi2"] = f"https://{bucket_name}.s3.amazonaws.com/{image['id']}_msavi2.tif"
        table.put_item(Item=location_data)

        return {
            "statusCode": 200,
            "message": "Image processed successfully.",
            "ndmi": f"{image['id']}_ndmi.tif",
            "msavi2": f"{image['id']}_msavi2.tif"
        }
    else:
        logger.error("No suitable Sentinel-2 image found for the given parameters.")
        return {
            "statusCode": 404,
            "message": "No suitable image found."
        }

if __name__ == "__main__":
    handler({"httpMethod":"POST"}, {})
