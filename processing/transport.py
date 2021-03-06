import json
from time import sleep
from flask_login import current_user
from backend.rabbitmq import rabbit_consumer
from backend.rabbitmq import rabbit_producer

from models.transport import Transport
from processing.api_key import new_api_key, get_api_key
from processing.error_message import create_error_message
from logger import log


def transport_json(transport):
    log("transport_json", "working on transport: {0}".format(transport))
    log("transport_json", "getting api key with id: {0}".format(transport.ApiKeyId))
    apiKey = get_api_key(transport.ApiKeyId)
    log("transport_json", "got apiKey: {0}".format(apiKey))
    apiKeyName = apiKey["Results"][0]["Name"]


    created = None
    if transport.Created:
        created = transport.Created.isoformat()

    lastCheckin = None
    if transport.LastCheckin:
        lastCheckin = transport.LastCheckin.isoformat()

    return {
        "Id": transport.Id,
        "Name": transport.Name,
        "Guid": transport.Guid,
        "TransportType": transport.TransportType,
        "ApiKeyId": transport.ApiKeyId,
        "ApiKeyName": apiKeyName,
        "Created": created,
        "LastCheckin": lastCheckin,
        "Enabled": transport.Enabled,
        "Visible": transport.Visible,
        "Configuration": transport.Configuration
    }


def get_transport(transport_id='all', include_hidden=False):
    log("transport.py:get_transport", "got transport id: {0}".format(transport_id))
    results = []
    transports = []
    if transport_id == 'all':
        if include_hidden:
            transports = Transport.query.all()
        else:
            transports = Transport.query.filter_by(Visible=True)
    else:
        transports.append(Transport.query.get(transport_id))
    for transport in transports:
        results.append(transport_json(transport))
    return {
        "Success": 'True',
        "Results": results
    }


def new_transport(name):
    apiKey = new_api_key('transport', 1, current_user.Id)
    publish_message = dict({
        "Name": name,
        "ApiKeyId": apiKey["Id"],
        "UserId": current_user.Id
    })

    log("transport:new_transport", "Publishing: {0}".format(publish_message))
    message_id = rabbit_producer.send_request("NewTransport", publish_message, callback=True)

    # Wait for our response
    # TODO: Add actual timeout here.
    i = 0
    while i < 20:
        log("transport:new_transport", "Waiting for {0} seconds".format(20 - i))
        sleep(1)
        i += 1

        # Return data
        log("transport:new_transport", "queue: {}".format(rabbit_consumer.queue))
        message = rabbit_consumer.queue.get(message_id)
        if message:
            log("transport:new_transport", "Got response from Core: {0}".format(message))
            message_dict = json.loads(message)

            if 'Transport' in message_dict.keys():

                transport = Transport.query.get(message_dict['Transport']['Id'])
                return {
                    "Success": True,
                    "TransportId": transport.Id,
                    "ApiKey": {
                        "KeyName": apiKey["Name"],
                        "Secret": apiKey["Secret"]
                    },
                    "Transport": transport_json(transport)
                }
    log("transport:new_transport", "Timed out.")
    return create_error_message(
        "Timeout waiting for response from Core while creating new transport. Resubmit your request.")


def update_transport(transport_id, name=None, transport_type=None, guid=None, configuration=None, enabled=None, visible=None):
    transport = Transport.query.get(transport_id)

    # Only update what we're given. Probably a better way to do this..
    if name is None:
        name = transport.Name

    if transport_type is None:
        transport_type = transport.TransportType

    if guid is None:
        guid = transport.Guid

    if configuration is None:
        configuration = transport.Configuration

    if enabled is None:
        enabled = transport.Enabled

    if visible is None:
        visible = transport.Visible

    publish_message = {
        "Id": transport.Id,
        "Name": name,
        "TransportType": transport_type,
        "Guid": guid,
        "Configuration": configuration,
        "Enabled": enabled,
        "Visible": visible
    }

    message_id = rabbit_producer.send_request("UpdateTransport", publish_message, callback=True)
    # Wait for our response
    # TODO: Add actual timeout here.
    i = 0
    while rabbit_consumer.queue[message_id] is None and i < 15:
        log("transport:new_transport", "Waiting for {0} seconds".format(15 - i))
        sleep(1)
        i += 1

    # Return data
    message = rabbit_consumer.queue[message_id]

    if message:
        return json.loads(message)
    else:
        log("transport:update_transport", "Timed out.")
        return create_error_message("Timeout waiting for response from Core while updating transport. Resubmit your request.")