from os import path

HOST = "0.0.0.0"
PORT = 9998

BASE_DIR = path.dirname(path.dirname(path.abspath(__file__)))
USER_HOME_DIR = path.join(BASE_DIR,'home')
ACCOUNT_FILE = "%s/conf/accounts.ini" % BASE_DIR