from django.conf import settings


def get_twilio_client():
    from twilio.rest import Client

    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
