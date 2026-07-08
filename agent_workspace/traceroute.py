import socket
import sys
import struct

def traceroute(dest_addr, max_hops=30, timeout=3):
    try:
        dest_ip = socket.gethostbyname(dest_addr)
    except socket.gaierror:
        print(f"无法解析目标地址: {dest_addr}")
        return
    
    print(f"路由追踪到 {dest_addr} ({dest_ip})，最多 {max_hops} 跳:\n")
    
    for ttl in range(1, max_hops + 1):
        # 发送端 UDP socket
        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
        send_sock.settimeout(timeout)
        
        # 接收端 ICMP socket
        recv_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        recv_sock.settimeout(timeout)
        
        # 使用一个随机的高端口
        port = 33434 + ttl
        
        start_time = None
        try:
            start_time = __import__('time').time()
            send_sock.sendto(b'', (dest_ip, port))
            
            try:
                data, addr = recv_sock.recvfrom(512)
                elapsed = (__import__('time').time() - start_time) * 1000
                
                # 解析 ICMP 头部获取类型
                icmp_type = data[20] if len(data) > 20 else None
                icmp_code = data[21] if len(data) > 21 else None
                
                curr_addr = addr[0]
                try:
                    hostname = socket.gethostbyaddr(curr_addr)[0]
                except:
                    hostname = curr_addr
                
                print(f"  {ttl:2d}.  {hostname} ({curr_addr})  {elapsed:.1f} ms")
                
                # ICMP type 0 = Echo Reply (到达目标)
                # ICMP type 3 = Destination Unreachable (到达目标或端口不可达)
                if curr_addr == dest_ip or icmp_type == 0 or (icmp_type == 3 and icmp_code == 3):
                    print(f"\n✅ 到达目标 {dest_ip}")
                    break
                    
            except socket.timeout:
                print(f"  {ttl:2d}.  * * *  (超时)")
                
        except Exception as e:
            print(f"  {ttl:2d}.  * * *  (错误: {e})")
        finally:
            send_sock.close()
            recv_sock.close()
    else:
        print(f"\n⚠️ 已到达最大跳数 {max_hops}，未到达目标")

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else "8.8.8.8"
    traceroute(target)
