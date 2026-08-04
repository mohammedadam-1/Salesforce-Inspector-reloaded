import inspect
import fastapi
import starlette

print("fastapi", fastapi.__version__, "starlette", starlette.__version__)
import fastapi.openapi.docs as d

print("get_swagger_ui_html:", inspect.signature(d.get_swagger_ui_html))
print("get_redoc_html:", inspect.signature(d.get_redoc_html))
