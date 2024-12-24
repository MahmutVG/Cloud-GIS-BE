import boto3
import os
import logging
from botocore.exceptions import ClientError
import numpy as np
from osgeo import gdal
from dotenv import load_dotenv
import requests

load_dotenv()
s3 = boto3.client('s3')
logger = logging.getLogger()
logger.setLevel(logging.INFO)
gdal.UseExceptions()

from sklearn.cluster import KMeans

def calculate_ndmi(nir_path, swir_path, *args, **kwargs):
    logger.info(f"Calculating NDMI for NIR: {nir_path}, SWIR: {swir_path}")
    nir_ds = gdal.Open(nir_path)
    swir_ds = gdal.Open(swir_path)
    
    nir_band = nir_ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
    swir_band = swir_ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
    
    ndmi = (nir_band - swir_band) / (nir_band + swir_band)
    
    ndmi_band = "/tmp/ndmi.tif"
    driver = gdal.GetDriverByName('GTiff')
    out_ds = driver.Create(ndmi_band, nir_ds.RasterXSize, nir_ds.RasterYSize, 1, gdal.GDT_Float32)
    out_ds.SetGeoTransform(nir_ds.GetGeoTransform())
    out_ds.SetProjection(nir_ds.GetProjection())
    out_ds.GetRasterBand(1).WriteArray(ndmi)
    out_ds = None
    
    logger.info(f"NDMI calculation completed: {ndmi_band}")
    return ndmi_band

def calculate_msavi2(nir_path, red_path, *args, **kwargs):
    logger.info(f"Calculating MSAVI2 for NIR: {nir_path}, RED: {red_path}")
    nir_ds = gdal.Open(nir_path)
    red_ds = gdal.Open(red_path)
    
    nir_band = nir_ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
    red_band = red_ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
    
    msavi2 = (2 * nir_band + 1 - np.sqrt((2 * nir_band + 1)**2 - 8 * (nir_band - red_band))) / 2
    
    msavi2_band = "/tmp/msavi2.tif"
    driver = gdal.GetDriverByName('GTiff')
    out_ds = driver.Create(msavi2_band, nir_ds.RasterXSize, nir_ds.RasterYSize, 1, gdal.GDT_Float32)
    out_ds.SetGeoTransform(nir_ds.GetGeoTransform())
    out_ds.SetProjection(nir_ds.GetProjection())
    out_ds.GetRasterBand(1).WriteArray(msavi2)
    out_ds = None
    
    logger.info(f"MSAVI2 calculation completed: {msavi2_band}")
    return msavi2_band

def process_image(msavi2, ndmi, output_bucket_name):
    logger.info(f"Processing image with MSAVI2: {msavi2}, NDMI: {ndmi}")
    try:
        msavi2 = gdal.Open(msavi2)
        ndmi = gdal.Open(ndmi)

        kmeans = KMeans(n_clusters=6)
        kmeans.fit(np.column_stack((msavi2.GetRasterBand(1).ReadAsArray().ravel(), ndmi.GetRasterBand(1).ReadAsArray().ravel())))
        labels = kmeans.labels_
        unique_labels = np.unique(labels)
        labels = labels.reshape(msavi2.RasterYSize, msavi2.RasterXSize)
        logger.info(f"KMeans clustering completed. Unique labels: {unique_labels}")

        driver = gdal.GetDriverByName('GTiff')
        
        output_ds = driver.Create("/tmp/labels.tif", msavi2.RasterYSize, msavi2.RasterXSize, 1, gdal.GDT_Byte)
        output_ds.SetGeoTransform(msavi2.GetGeoTransform())
        output_ds.SetProjection(msavi2.GetProjection())
        output_ds.GetRasterBand(1).WriteArray(labels)
        output_ds = None
        
        logger.info("Labels image created: /tmp/labels.tif")
        
        if output_bucket_name:
            s3.upload_file('/tmp/labels.tif', output_bucket_name, 'labels.tif')
            logger.info(f"Labels image uploaded to S3 bucket: {output_bucket_name}")
        
        return True
    except ClientError as e:
        logger.error(e)
        return False

def resample_band(input_path, x_res, y_res):
    logger.info(f"Resampling band: {input_path} to resolution ({x_res}, {y_res})")
    input_ds = gdal.Open(input_path)
    
    out_path = input_path.replace('.tif', '_resampled.tif')
    
    gdal.Warp(out_path, input_ds, xRes=x_res, yRes=y_res)
    os.remove(input_path)
    input_ds = None
    logger.info(f"Resampling completed: {out_path}")
    return out_path

def handler(event, context):
    logger.info(f"Handler invoked with event: {event}")
    date = event.get('date', "2024-01-01T00:00:00.000Z/2024-03-05T00:00:00.000Z")
    coords = event.get('coordinates', "37.0463,31.1018")
    logger.info(f"Coordinates: {coords}")
    bbox = generate_bbox_from_lat_lon(*map(float, coords.split(',')), 0.00000001)
    logger.info(f"Generated bbox: {bbox}")
    sentinel_handler(date, bbox)

def get_sentinel_image(date, bbox):
    logger.info(f"Fetching Sentinel image for date: {date}, bbox: {bbox}")
    url = f"https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items?limit=12&datetime={date}&bbox={bbox}"
    response = requests.get(url)
    if response.status_code == 200:
        images = response.json()["features"]
        sorted_images = sorted(images, key=lambda x: x['properties']['eo:cloud_cover'])
        one_image = sorted_images[0] if sorted_images else None
        if one_image:
            logger.info(f"Selected image: {one_image['id']}")
            nir = one_image["assets"]["nir"]["href"]
            swir = one_image["assets"]["swir22"]["href"]
            red = one_image["assets"]["red"]["href"]
            for band in [nir, swir, red]:
                local_file = f'/tmp/{one_image["id"]}_{os.path.basename(band)}'
                if not os.path.exists(local_file):
                    response = requests.get(band)
                    with open(local_file, 'wb') as f:
                        f.write(response.content)
                    logger.info(f"Downloaded band: {local_file}")
            return {
                "nir_path": f'/tmp/{one_image["id"]}_B08.tif',
                "swir_path": f'/tmp/{one_image["id"]}_B12.tif',
                "red_path": f'/tmp/{one_image["id"]}_B04.tif'
            }
    logger.error("Failed to fetch Sentinel image")
    return None

def sentinel_handler(date, bbox):
    logger.info(f"Sentinel handler invoked for date: {date}, bbox: {bbox}")
    sentinel_image = get_sentinel_image(date, bbox)
    if sentinel_image:
        sentinel_image['swir_path'] = resample_band(sentinel_image['swir_path'], 10, 10)
        msavi2 = calculate_msavi2(**sentinel_image)
        ndmi = calculate_ndmi(**sentinel_image)

        process_image(msavi2, ndmi, os.getenv('OUTPUT_BUCKET_NAME'))
    else:
        logger.error("No images found")

def generate_bbox_from_lat_lon(lat, lon, radius):
    bbox = f"{lon - radius},{lat - radius},{lon + radius},{lat + radius}"
    logger.info(f"Generated bbox from lat: {lat}, lon: {lon}, radius: {radius} -> {bbox}")
    return bbox

if __name__ == "__main__":
    handler({})