from app import SetupError, logger

try:
    raise SetupError('Bad news')
except:
    logger.error('City Analytics Dashboard - Self-harm error', exc_info=True)
