# Sentinel Data Processing

This project provides a set of tools for processing Sentinel-2 satellite images using AWS Lambda. It includes functionality for calculating vegetation indices, clustering image data, and handling image downloads from an API.

## Project Structure

- `src/sentinel_data.py`: Contains the main logic for processing Sentinel-2 satellite images. It includes functions for calculating NDMI and MSAVI2 indices, processing images using KMeans clustering, downloading images from a specified API, and handling AWS Lambda events.
  
- `requirements.txt`: Lists the Python dependencies required for the project, including libraries such as `boto3`, `numpy`, `gdal`, `requests`, and `sklearn`.

- `.env`: Used to store environment variables, such as AWS credentials and configuration settings for the Lambda function.

## Setup Instructions

1. Clone the repository:
   ```
   git clone <repository-url>
   cd lambda-sentinel-data
   ```

2. Create a virtual environment and activate it:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Configure your environment variables in the `.env` file. Ensure you include your AWS credentials and any other necessary configuration settings.

## Usage

To deploy the Lambda function, package the contents of the `src` directory and upload it to AWS Lambda. Ensure that the Lambda function has the necessary permissions to access S3 and any other AWS services you intend to use.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.