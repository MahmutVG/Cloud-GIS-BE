import boto3
import json
import logging
from decimal import Decimal
import uuid

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
    if http_method == 'POST':
        return create_location(event)
    elif http_method == 'GET':
        return get_all_locations()
    else:
        logger.warning("Unsupported HTTP method: %s", http_method)
        return {
            'statusCode': 405,
            'body': json.dumps({'message': 'Method not allowed'})
        }

def create_location(event):
    try:
        logger.info("Processing POST request")
        
        # Parse the JSON body
        data = json.loads(event['body'])
        logger.info("Parsed body: %s", data)
        
        # Generate a unique UUID for the location
        location_id = str(uuid.uuid4())
        
        # Convert latitude/longitude to Decimal for DynamoDB
        new_item = {
            "LocationID": location_id,
            "name": data['name'],  # Use parsed data instead of undefined body
            "coordinates" : {
                "lat": Decimal(str(data['coordinates']['lat'])),
                "lon": Decimal(str(data['coordinates']['lon']))
            },
            "description": data['description'],
            "status": "POINT_CREATED"
        }
        
        # Insert the item into DynamoDB
        logger.info("Inserting item into DynamoDB: %s", new_item)
        table.put_item(Item=new_item)
        
        logger.info("Location created successfully with ID: %s", location_id)
        return {
            'statusCode': 201,
            'body': json.dumps({'message': 'Location created', 'location_id': location_id})
        }
    except Exception as e:
        logger.error("Error occurred while creating location: %s", str(e), exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Internal server error', 'error': str(e)})
        }

def get_all_locations():
    try:
        logger.info("Processing GET request")
        
        # Scan DynamoDB for all locations
        response = table.scan()
        locations = response.get('Items', [])
        logger.info("Retrieved locations: %s", locations)
        
        return {
            'statusCode': 200,
            'body': json.dumps({'locations': locations}, cls=DecimalEncoder)
        }
    except Exception as e:
        logger.error("Error occurred while retrieving locations: %s", str(e), exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Internal server error', 'error': str(e)})
        }
