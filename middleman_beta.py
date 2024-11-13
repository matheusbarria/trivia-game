import socket
import selectors
import multiprocessing
import threading
import json
import random
import string
import logging
from concurrent.futures import ThreadPoolExecutor

# Logger configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# Directory to store active application servers and room details
application_servers = {}  # Format: {'service_name': ('ip', port)}
rooms = {}  # Format: {'join_code': RoomProcess}

# Room Process Class
class RoomProcess(multiprocessing.Process):
    def __init__(self, join_code, client_socket, app_server_addr):
        super().__init__()
        self.join_code = join_code
        self.client_sockets = {client_socket.fileno(): client_socket}
        self.app_server_addr = app_server_addr
        self.sel = selectors.DefaultSelector()
        self.app_socket = None

    def run(self):
        try:
            # Establish connection to the application server
            self.app_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.app_socket.connect(self.app_server_addr)
            self.sel.register(self.app_socket, selectors.EVENT_READ, self.handle_app_server)
            logging.info(f"Connected to application server for room {self.join_code}.")

            # Register client sockets for room communication
            for sock in self.client_sockets.values():
                self.sel.register(sock, selectors.EVENT_READ, self.handle_client)

            # Run the event loop
            while True:
                events = self.sel.select(timeout=1)
                for key, _ in events:
                    callback = key.data
                    callback(key.fileobj)
                
                if not self.client_sockets:
                    logging.info(f"Closing room {self.join_code} as no clients are connected.")
                    self.close_room()
                    break

        except Exception as e:
            logging.error(f"Room {self.join_code} encountered an error: {e}")
        finally:
            self.cleanup()

    def handle_client(self, client_socket):
        try:
            data = client_socket.recv(1024)
            if data:
                # Relay client data to application server
                if self.app_socket:
                    self.app_socket.sendall(data)
            else:
                # Handle client disconnection
                logging.info(f"Client in room {self.join_code} disconnected.")
                self.remove_client(client_socket)

        except (ConnectionError, OSError):
            logging.info(f"Client in room {self.join_code} disconnected unexpectedly.")
            self.remove_client(client_socket)

    def handle_app_server(self, app_socket):
        try:
            data = app_socket.recv(1024)
            if data:
                # Relay data to all connected clients in the room
                for client_socket in self.client_sockets.values():
                    client_socket.sendall(data)
            else:
                # Close the room if application server disconnects
                logging.error(f"Application server for room {self.join_code} disconnected.")
                self.close_room()
        except (ConnectionError, OSError):
            logging.error(f"Application server for room {self.join_code} encountered a connection error.")
            self.close_room()

    def add_client(self, client_socket):
        self.client_sockets[client_socket.fileno()] = client_socket
        self.sel.register(client_socket, selectors.EVENT_READ, self.handle_client)

    def remove_client(self, client_socket):
        self.client_sockets.pop(client_socket.fileno(), None)
        self.sel.unregister(client_socket)
        client_socket.close()

    def close_room(self):
        for client_socket in self.client_sockets.values():
            self.sel.unregister(client_socket)
            client_socket.close()
        if self.app_socket:
            self.sel.unregister(self.app_socket)
            self.app_socket.close()
        self.sel.close()
        rooms.pop(self.join_code, None)
        logging.info(f"Room {self.join_code} closed.")

    def cleanup(self):
        self.close_room()
        logging.info(f"Cleaned up resources for room {self.join_code}.")

# Main Middleman Server Class
class MiddlemanServer:
    def __init__(self, host='0.0.0.0', port=5000, max_threads=10):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((host, port))
        self.server_socket.listen()
        self.executor = ThreadPoolExecutor(max_workers=max_threads)
        logging.info(f"Middleman server started on {self.host}:{self.port}")

    def handle_new_client(self, client_socket):
        try:
            request = json.loads(client_socket.recv(1024).decode())
            action = request.get('action')
            if action == 'create_room':
                self.create_room(client_socket, request)
            elif action == 'join_room':
                self.join_room(client_socket, request)
            else:
                client_socket.send(json.dumps({'status': 'error', 'message': 'Unknown action'}).encode())
        except (json.JSONDecodeError, KeyError) as e:
            logging.error(f"Invalid request from client: {e}")
            client_socket.send(json.dumps({'status': 'error', 'message': 'Invalid request format'}).encode())
        except Exception as e:
            logging.error(f"Error handling client request: {e}")
        finally:
            client_socket.close()

    def create_room(self, client_socket, request):
        join_code = self.generate_join_code()
        app_server = application_servers.get(request['service_name'])
        if app_server:
            # Start new room process
            room = RoomProcess(join_code, client_socket, app_server)
            rooms[join_code] = room
            room.start()
            client_socket.send(json.dumps({'status': 'success', 'join_code': join_code}).encode())
            logging.info(f"Room {join_code} created for service {request['service_name']}.")
        else:
            client_socket.send(json.dumps({'status': 'error', 'message': 'Service unavailable'}).encode())

    def join_room(self, client_socket, request):
        join_code = request.get('join_code')
        room = rooms.get(join_code)
        if room:
            room.add_client(client_socket)
            client_socket.send(json.dumps({'status': 'success'}).encode())
            logging.info(f"Client joined room {join_code}.")
        else:
            client_socket.send(json.dumps({'status': 'error', 'message': 'Invalid join code'}).encode())
            logging.warning(f"Join attempt with invalid code: {join_code}")

    def generate_join_code(self, length=6):
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

    def accept_connections(self):
        while True:
            client_socket, _ = self.server_socket.accept()
            self.executor.submit(self.handle_new_client, client_socket)

    def register_application_server(self, service_name, address):
        application_servers[service_name] = address
        logging.info(f"Registered application server {service_name} at {address}")

# Server Entry Point
if __name__ == '__main__':
    middleman_server = MiddlemanServer()
    # Register available application servers
    middleman_server.register_application_server('trivia', ('127.0.0.1', 6000))
    middleman_server.register_application_server('battleship', ('127.0.0.1', 6001))
    # Start accepting connections from clients
    middleman_server.accept_connections()
