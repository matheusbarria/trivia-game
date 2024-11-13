from http.server import BaseHTTPRequestHandler, HTTPServer
import socket
import threading
import json
import random
import string
import logging

# Updated RoomProcess to handle HTTP requests for multiple endpoints
class RoomProcess(HTTPServer):
    def __init__(self, join_code, host, port, app_servers):
        # Each room process has its join code, binds to a unique port, and connects to specific app servers
        super().__init__((host, port), RoomRequestHandler)
        self.join_code = join_code
        self.app_servers = app_servers  # {'trivia': ('ip', port), 'battleship': ('ip', port)}
        self.active_connections = {}

    def run(self):
        logging.info(f"Starting room {self.join_code} server on port {self.server_address[1]}")
        self.serve_forever()

    def connect_to_app_server(self, endpoint):
        # Establish a connection to the appropriate application server based on the endpoint
        app_server_addr = self.app_servers.get(endpoint)
        if app_server_addr and endpoint not in self.active_connections:
            sock = socket.create_connection(app_server_addr)
            self.active_connections[endpoint] = sock
            logging.info(f"Connected to {endpoint} app server for room {self.join_code}")
        return self.active_connections.get(endpoint)

class RoomRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        endpoint = self.path.lstrip('/')  # Determine the endpoint from the URL path
        app_server_sock = self.server.connect_to_app_server(endpoint)
        
        if not app_server_sock:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Application endpoint not found.")
            return

        # Send a request to the app server and get the response
        try:
            # Example request message to app server
            app_server_sock.sendall(b"GET request to endpoint")
            response = app_server_sock.recv(4096)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(response)
        except Exception as e:
            logging.error(f"Error communicating with app server for {endpoint}: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Internal server error.")

    def log_message(self, format, *args):
        return  # Suppress default logging

# Main Middleman Server with HTTP endpoint handling
class MiddlemanServer:
    def __init__(self, host='0.0.0.0', port=5000):
        self.host = host
        self.port = port
        self.application_servers = {
            'trivia': ('127.0.0.1', 6000),
            'battleship': ('127.0.0.1', 6001)
        }
        self.rooms = {}

    def create_room(self, client_socket, request):
        join_code = self.generate_join_code()
        room_port = random.randint(10000, 20000)  # Assign a unique port for the room process
        room = RoomProcess(join_code, self.host, room_port, self.application_servers)
        self.rooms[join_code] = room
        threading.Thread(target=room.run).start()  # Run room server in a separate thread
        client_socket.send(json.dumps({'status': 'success', 'join_code': join_code, 'port': room_port}).encode())
        logging.info(f"Room {join_code} created on port {room_port}.")

    def generate_join_code(self, length=6):
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# Server Entry Point
if __name__ == '__main__':
    middleman_server = MiddlemanServer()
    logging.info("Middleman server started.")
    # Run middleman_server's client connection handling here
