from os import path
import socketserver
HOST = "0.0.0.0"
PORT = 9999

BASE_DIR = path.dirname(path.dirname(path.abspath(__file__)))
USER_HOME_DIR = path.join(BASE_DIR,'home')
ACCOUNT_FILE = "%s/conf/accounts.ini" % BASE_DIR
MAXThread = 10
