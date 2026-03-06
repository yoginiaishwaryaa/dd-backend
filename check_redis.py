import socket

def find_redis_port(start_port=6000, end_port=6700):
    print(f"Scanning for Redis services on localhost ports {start_port}-{end_port}...")
    # Skipping common Windows ports to speed up scan
    skip_ports = {135, 443, 445, 5040, 5357, 5985, 49664, 49665, 49666, 49667, 49668, 49669}
    found = False
    for port in range(start_port, end_port + 1):
        if port in skip_ports:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.05) # Very fast scan
            result = s.connect_ex(('127.0.0.1', port))
            if result == 0:
                try:
                    s.sendall(b"*1\r\n$4\r\nPING\r\n")
                    response = s.recv(1024)
                    if b"PONG" in response or b"NOAUTH" in response:
                        print(f"\n[!] SUCCESS: Redis found on port {port}!")
                        print(f"Update your .env with: REDIS_URL=\"redis://localhost:{port}/0\"")
                        found = True
                        break 
                except Exception:
                    pass
        if port % 500 == 0:
            print(f"Progress: at port {port}...")
    
    if not found:
        print("\nNo Redis service found in the scanned range (1000-10000).")

if __name__ == "__main__":
    find_redis_port()
