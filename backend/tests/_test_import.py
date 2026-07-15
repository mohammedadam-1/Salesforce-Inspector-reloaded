import sys
sys.path.insert(0, 'src')
print('testing container import...')
from sfir_backend.config.container import Container
print('OK')
from sfir_backend.api.v1.routes import api_router
print('routes OK')
