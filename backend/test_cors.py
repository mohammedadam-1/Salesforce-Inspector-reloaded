from sfir_backend.main import create_app
from sfir_backend.config.settings import Settings
s = Settings()
app = create_app(s)
print("OK")
