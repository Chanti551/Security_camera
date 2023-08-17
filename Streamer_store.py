import tornado.web, tornado.ioloop, tornado.websocket
from general import WebSocketHandler, get_exec_dir, get_file_content
from buffers import StreamBuffer
from string import Template
import socket
import websockets
import asyncio
import subprocess
import os
import datetime
import numpy as np

# Class that is responsible for streaming the camera footage to the web-page.
class Streamer:
    def __init__(self, camera, h264_args, streaming_resolution='640x480', fps=30, port=8000):
        self.camera = camera
        self.h264_args = h264_args
        self.streaming_resolution = streaming_resolution
        self.fps = fps
        self.server_port = port
        self.server_ip = self._socket_setup()

        self.request_handlers = None

    # Set up the request handlers for tornado.
    def _setup_request_handlers(self):
        parent = self

        # Handler for the javascript of the streaming page.
        class JSHandler(tornado.web.RequestHandler):
            def get(self):
                self.write(Template(get_file_content('web/index.js')).substitute({'ip': parent.server_ip, 'port': parent.server_port, 'fps': parent.fps}))

        self.request_handlers = [
            (r"/ws/", WebSocketHandler),
            (r"/index.js", JSHandler),
            (r"/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(get_exec_dir(), "web/static/")})
        ]

    # Set up the web socket.
    def _socket_setup(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 0))
        server_ip = s.getsockname()[0]
        return server_ip

    # Start streaming.
    def start(self):
        self._setup_request_handlers()
        try:

            stream_buffer = StreamBuffer(self.camera)
            self.camera.start_recording(stream_buffer, splitter_port=2, **self.h264_args, resize=self.streaming_resolution)

            # Create and loop the tornado application.
            application = tornado.web.Application(self.request_handlers)
            application.listen(self.server_port)
            loop = tornado.ioloop.IOLoop.current()
            stream_buffer.setLoop(loop)
            print("Streamer started on http://{}:{}/index.html".format(self.server_ip, self.server_port))
            asyncio.get_event_loop().run_until_complete(connect_to_websocket(self.server_ip,self.server_port))
            loop.start()
                
        except KeyboardInterrupt:
            self.camera.stop_recording()
            self.camera.close()
            loop.stop()


async def connect_to_websocket(ip,port):
    uri = f"ws://{ip}:{port}/ws/"  # Replace with your WebSocket server URI
    current_date=None
    folder_name = None
    file_path = None
    
    while True:
        current_time = datetime.datetime.now()
        
        if current_time.date() != current_date:  # Check if a new day has started
            current_date = current_time.date()
            folder_name = current_date.strftime("%Y-%m-%d")
            os.makedirs(f"h264videos/{folder_name}", exist_ok=True)  # Create a new folder for each day

        if folder_name:
            if file_path:
                os.rename(file_path, os.path.join(f"h264videos/{folder_name}", file_path))
            file_path = current_time.strftime('%H-%M-%S') + ".h264"
        
        async with websockets.connect(uri) as websocket:
            video_file = open(os.path.join(f"h264videos/{folder_name}", file_path), "ab")  # Open a file to store the H.264 data (append mode)
            try:
                while True:
                    frame_data = await websocket.recv()
                    video_file.write(frame_data)  # Write the received H.264 frame to the file
            finally:
                video_file.close()  # Close the file when done6
