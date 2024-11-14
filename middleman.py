import socket
import logging


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')


class MiddlemanServer:
    application_servers = {}  # Format: {'service_name': ('ip', port)}
    rooms = {}  # Format: {'join_code': RoomProcess}

    def __init__(self, host='127.0.0.1', port=5000, max_threads=10):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        # self.server_socket.bind((socket.gethostname(), port))
        # self.server_socket.listen()
        self.location = self.server_socket.getsockname()
        # self.executor = ThreadPoolExecutor(max_workers=max_threads)
        logging.info(f"Middleman server started on {self.host}:{self.port}")
        print(f'Listening on port {self.location}')

    def handle_http_request(self,request_bytes):
        request_str = request_bytes.decode()
        request_lines = request_str.split('\r\n')
        request_line = request_lines[0].split(' ')
        method = request_line[0]
        path = request_line[1]
        # Log the request details
        print(f"Method: {method}, Path: {path}")

        if method == 'GET' and path == '/':
            html_content = '''
            <html>
            <head><title>Event Rooms</title></head>
            <body style="text-align: center;">
            <h1>Event Rooms!</h1>
            <ol> {application_servers} </ol>
            <form method="POST" action="/">
                <label for="server_number">Enter Server Number:</label>
                <input type="text" id="server_number" name="server_number" required> <input type="submit" value="Submit">
            </form>
            </body>
            </html> '''
            application_servers_list = ''.join(f'<li>{server}</li>' for server in self.application_servers)
            html_content = html_content.format(application_servers=application_servers_list)
            return b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + html_content.encode()
        elif method == 'POST' and path == '/':
            body = request_str.split('\r\n\r\n')[1]
            params = body.split('&')
            data = {k: v for k, v in (param.split('=') for param in params)}
            server_number = data.get('server_number')
            if server_number:
                response_content = f'<html><body><h1>Received Server Number: {server_number}</h1></body></html>'
                return b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + response_content.encode()
            else: return b"HTTP/1.1 400 Bad Request\r\nContent-Type: text/html\r\n\r\n<html><body><h1>Bad Request</h1></body></html>"
        else:
            return b"HTTP/1.1 404 Not Found\r\nContent-Type: text/html\r\n\r\n<html><body><h1>404 Not Found</h1></body></html>"
    
    def accept_connections(self):
        while True:
            self.server_socket.listen(2) # play with this val
            sock, client_address = self.server_socket.accept()
            try:
                data = sock.recv(1024)
                print(data)
                print()
            except Exception as ex:
                print(ex)
            resp = self.handle_http_request(data)
            sock.sendall(resp)
    
    def register_application_server(self, service_name, address):
        self.application_servers[service_name] = address
        logging.info(f"Registered application server {service_name} at {address}")


if __name__ == '__main__':
    middleman_server = MiddlemanServer()
    # Register available application servers
    middleman_server.register_application_server('trivia', ('127.0.0.1', 6000))
    middleman_server.register_application_server('battleship', ('127.0.0.1', 6001))
    # Start accepting connections from clients
    middleman_server.accept_connections()