import os

from aiohttp import ClientSession, web

from bridger.meshtastic import DeviceModel

VERSION = os.getenv("SENTRY_RELEASE", "development")

routes = web.RouteTableDef()
device = None
session = None


def create_app():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.add_routes(routes)
    return app


async def on_startup(app):
    global device, session
    session = ClientSession()
    device = DeviceModel(session=session)


async def on_cleanup(app):
    await session.close()


@routes.get("/")
async def index_view(request):
    app = request.app
    # Get list of routes and their methods
    routes_list = [(route.method, route.resource.canonical) for route in app.router.routes()]

    if "application/json" in request.headers.get("Accept", ""):
        routes_list = [{"method": method, "path": path} for method, path in routes_list]
        return web.json_response(routes_list)

    # return HTML response if not curl
    if "curl" in request.headers.get("User-Agent", ""):
        routes_list = [f"{method} {path}" for method, path in routes_list]
        routes_list = "\n".join(routes_list)
        return web.Response(text=routes_list, content_type="text/plain")

    html_response = "<h1>Bridger API</h1><ul>"
    for method, path in routes_list:
        html_response += f"<li>{method} {path}</li>"
    html_response += "</ul>"
    html_response += f"<p>Version: {VERSION}</p>"

    return web.Response(text=html_response, content_type="text/html")


@routes.get("/model/displaynames/{model_id}")
async def get_displaynames(request):
    model_id = int(request.match_info["model_id"])
    displaynames = await device.get_displaynames(model_id)
    return web.json_response(displaynames)


@routes.get("/model/displaynames")
async def get_displaynames_all(request):
    displaynames = await device.get_all_displaynames()
    return web.json_response(displaynames)


@routes.get("/health")
async def health_check(request):
    return web.json_response({"status": "ok", "version": VERSION})


if __name__ == "__main__":
    web.run_app(create_app())
