import os
import socket

os.environ["WSGI_HANDLER"] = "test"
os.environ.pop("BALE_TOKEN", None)
os.environ.pop("BALE_CHAT_ID", None)

# Block outbound network connections in this test process.
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_create_connection = socket.create_connection

def blocked_connect(self, address):
    raise RuntimeError("TEST MODE: Outbound network blocked")

def blocked_connect_ex(self, address):
    raise RuntimeError("TEST MODE: Outbound network blocked")

def blocked_create_connection(*args, **kwargs):
    raise RuntimeError("TEST MODE: Outbound network blocked")

socket.socket.connect = blocked_connect
socket.socket.connect_ex = blocked_connect_ex
socket.create_connection = blocked_create_connection

import app as application_module
import bale_service
import assigned_checklists

def disabled_service(*args, **kwargs):
    print("TEST MODE: Background service disabled")

def disabled_bale(*args, **kwargs):
    print("TEST MODE: Bale message suppressed")

application_module.init_tcp_server = disabled_service
application_module.start_scheduler = disabled_service
application_module.bale_worker = disabled_service

bale_service.send_to_bale_async = disabled_bale
assigned_checklists.send_to_bale_async = disabled_bale

app = application_module.create_app()

if __name__ == "__main__":
    print("TEST SERVER: http://127.0.0.1:5055")
    app.run(
        host="127.0.0.1",
        port=5055,
        debug=False,
        use_reloader=False,
        threaded=True
    )
