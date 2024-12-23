import boto3
import json
import logging
from decimal import Decimal

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB setup
dynamodb = boto3.resource('dynamodb')
table_name = 'MapLocations'
table = dynamodb.Table(table_name)

# Custom JSON Encoder for Decimal
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def lambda_handler(event, context):
    logger.info("Event received: %s", json.dumps(event))  # Log the event for debugging
    
    http_method = event['httpMethod']
    location_id = event['pathParameters']['uuid']
    
    if http_method == 'GET':
        return get_location_by_uuid(location_id)
    elif http_method == 'DELETE':
        return delete_location_by_uuid(location_id)
    elif http_method == 'PUT':
        return update_location_by_uuid(location_id, event)
    else:
        logger.warning("Unsupported HTTP method: %s", http_method)
        return {
            'statusCode': 405,
            'body': json.dumps({'message': 'Method not allowed'})
        }

def get_location_by_uuid(location_id):
    try:
        logger.info("Processing GET request for location ID: %s", location_id)
        
        # Get the item from DynamoDB
        response = table.get_item(Key={'LocationID': location_id})
        item = response.get('Item')
        
        if not item:
            logger.warning("Location not found with ID: %s", location_id)
            return {
                'statusCode': 404,
                'body': json.dumps({'message': 'Location not found'})
            }
        
        logger.info("Retrieved location: %s", item)
        return {
            'statusCode': 200,
            'body': json.dumps(item, cls=DecimalEncoder)
        }
    except Exception as e:
        logger.error("Error occurred while retrieving location: %s", str(e), exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Internal server error', 'error': str(e)})
        }

def delete_location_by_uuid(location_id):
    try:
        logger.info("Processing DELETE request for location ID: %s", location_id)
        
        # Delete the item from DynamoDB
        table.delete_item(Key={'LocationID': location_id})
        
        logger.info("Location deleted successfully with ID: %s", location_id)
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Location deleted'})
        }
    except Exception as e:
        logger.error("Error occurred while deleting location: %s", str(e), exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Internal server error', 'error': str(e)})
        }

def update_location_by_uuid(location_id, event):
    try:
        logger.info("Processing PUT request for location ID: %s", location_id)
        
        # Parse the JSON body
        data = json.loads(event['body'])
        logger.info("Parsed body: %s", data)
        
        # Create the new item with the same LocationID
        updated_item = {
            "LocationID": location_id,
            "name": data['name'],
            "coordinates": {
                "lat": Decimal(str(data['coordinates']['lat'])),
                "lon": Decimal(str(data['coordinates']['lon']))
            },
            "description": data['description'],
        }
        
        # Insert the updated item into DynamoDB
        logger.info("Updating item in DynamoDB: %s", updated_item)
        table.put_item(Item=updated_item)
        
        logger.info("Location updated successfully with ID: %s", location_id)
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Location updated'})
        }
    except Exception as e:
        logger.error("Error occurred while updating location: %s", str(e), exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Internal server error', 'error': str(e)})
        }