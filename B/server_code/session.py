import time
import threading

sessions = {}
sessions_lock = threading.Lock()
server_seq_num = 0
