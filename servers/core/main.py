from conf import settings
from socket import *
import json,hashlib,time
import configparser
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
import queue

class Ftpserver(object):
    """处理客户端所有的交互的socket servers"""
    STATUS_CODE = {
        200: '认证通过',
        201: '账号密码错误',
        300: '路径错误',
        301: "文件存在,开始下载",
        302: '发送目录',
        303: '超过了磁盘限制',
        350: '目录已改变',
        351: '目录不存在',
        401: "文件存在，准备发送",
        402: "文件存在，大小错误",
    }

    MSG_SIZE = 1024     # 消息最长1024

    def __init__(self,management_instance):
        self.management_instance = management_instance
        # self.sock = socket(AF_INET,SOCK_STREAM)
        # self.sock.bind((settings.HOST,settings.PORT))
        # self.sock.listen(5)
        self.accounts = self.load_account()
        self.user_obj = None
        self.user_current_dir = None
        self.limit = None
        self.q = queue.Queue()

    def run_forever(self):
        """启动socket servers"""
        print('starting FTP servers on %s:%s'.center(50, '-') % (settings.HOST,settings.PORT))
        sock = socket(AF_INET, SOCK_STREAM)
        sock.bind((settings.HOST,settings.PORT))
        sock.listen(10)
        executor = ThreadPoolExecutor(settings.MAXThread)

        while True:
            request, addr = sock.accept()
            #print(self.request,self.addr)
            print("got a new connection form %s" % (addr,))
            try:
                executor.submit(self.handle)
                self.q.put(request)
                self.q.put(addr)
            except Exception as e:
                print("Error happend with client",e)
                request.close()

    def _auth(self,data):
        request = self.q.get()
        addr = self.q.get()
        #print("auth",data)
        if self.authenticate(data.get('username'),data.get('password')):
            print("通过认证")
            if not os.path.exists(os.path.join(settings.USER_HOME_DIR, data.get ('username'))):
                os.mkdir(os.path.join(settings.USER_HOME_DIR, data.get('username')))
            self.send_response(200,request,addr)
        else:
            print("通过失败")
            self.send_response(201,request,addr)

    def send_response(self,status_code,request,addr,*args,**kwargs):
        """打包发送消息给客户端"""
        data = kwargs
        data["status_code"] = status_code
        data['status_msg'] = self.STATUS_CODE[status_code]
        data['fill'] = ""
        b_data = json.dumps(data).encode()

        if len(b_data) < self.MSG_SIZE:
            data['fill'] = data['fill'].zfill(self.MSG_SIZE - len(b_data))
            b_data = json.dumps(data).encode("utf-8")
            request.send(b_data)

    def handle(self):
        """处理指令交互"""
        request = self.q.get()
        addr = self.q.get()
        print(request,addr)
        while True:
            raw_data = request.recv(self.MSG_SIZE)
            #print('-------->', raw_data)
            if not raw_data:
                print("%s连接丢失" % addr)
                del request,addr
                break
            data = json.loads(raw_data.decode("utf-8"))
            action_type = data.get('action_type')
            username = data.get('username')
            if action_type:
                if hasattr(self, "_%s"% action_type):
                    self.user_obj = self.accounts[username]
                    self.user_obj['home'] = os.path.join(settings.USER_HOME_DIR, username)
                    # print(self.user_obj['home'])
                    self.user_current_dir = self.user_obj['home']
                    self.limit = int(self.accounts[username]['limit'])
                    func = getattr(self, "_%s" % action_type)
                    self.q.put(request)
                    self.q.put(addr)
                    func(data)
            else:
                print("invalid command")

    def load_account(self):
        config_obj = configparser.ConfigParser()
        config_obj.read(settings.ACCOUNT_FILE)
        print(config_obj.sections())
        return config_obj

    def authenticate(self,username,password):
        """用户认证方法"""
        if username in self.accounts:
            _password = self.accounts[username]["password"]
            md5_obj = hashlib.md5()
            md5_obj.update(password.encode())
            print(md5_obj.hexdigest())
            if _password == md5_obj.hexdigest():
                self.user_obj = self.accounts[username]
                self.user_obj['home'] = os.path.join(settings.USER_HOME_DIR,username)
                #print(self.user_obj['home'])
                self.user_current_dir = self.user_obj['home']
                self.limit = int(self.accounts[username]['limit'])
                return True
            else:
                print("用户名或密码错误")
                return False

    def _get(self,data,):
        """下载文件
        1. 拿到文件名
        2. 判断文件是否存在
            2.1 存在返回状态码+大小
            2.2 不存在 返回状态码
        3.发送数据

        """
        request = self.q.get()
        addr = self.q.get()
        filename = data.get('filename')
        full_path = os.path.join(self.user_current_dir,filename)
        print(full_path)
        if os.path.isfile(full_path):
            filesize = os.stat(full_path).st_size
            self.send_response(301,request,addr,file_size=filesize)
            print("准备发送")
            f = open(full_path,'rb')
            for line in f:
                request.send(line)
            else:
                print("发送完成")
            f.close()
        else:
            self.send_response(300,request,addr)

    def _ls(self,data,):
        """返回文件目录"""
        request = self.q.get()
        addr = self.q.get()
        cmd_obj = subprocess.Popen('dir %s' % self.user_current_dir,shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        stdout = cmd_obj.stdout.read()
        stderr = cmd_obj.stderr.read()

        cmd_result = stdout + stderr
        #print(type(cmd_result))
        if not cmd_result:
            cmd_result = b'no list'

        self.send_response(302,request,addr,cmd_result_size=len(cmd_result))
        request.sendall(cmd_result)

    def _cd(self,data,):
        """根据请求值返回路径
        1.把target_dir和user_current_dir拼接
        2.检查要切换的目录是否存在
            2.1 存在 返回新路径的dir
            2.2 不存在 返回错误
        """
        request = self.q.get()
        addr = self.q.get()
        target_dir = data.get('target_dir')
        full_path = os.path.abspath(os.path.join(self.user_current_dir,target_dir))
        print(full_path)
        if os.path.isdir(full_path):
            if full_path.startswith(self.user_obj['home']):
                relative_current_dir = full_path.replace(self.user_obj['home'], "")
                self.user_current_dir = full_path
                self.send_response(350,request,addr,current=relative_current_dir)
            else:
                self.send_response(351,request,addr)
        else:
            self.send_response(351,request,addr)

    def _put(self,data):
        """上传文件到服务器
        1.拿到local文件名大小 判断是否超过限制
        2.检查本地是否有相应文件 self。user_current_dir/local_file
            2.1 文件存在
            2.2 文件不存在
        3.开始接收数据
        :param data:
        :return:
        """
        request = self.q.get()
        addr = self.q.get()
        local_file = data.get("filename")
        full_path = os.path.join(self.user_current_dir, local_file)  # 文件
        print(full_path)
        if os.path.isfile(full_path):  # 代表文件已存在，不能覆盖，
            filename = "%s.%s" % (full_path, time.time())
        else:
            filename = full_path

        f = open(filename, "wb")
        total_size = data.get('file_size')
        received_size = 0
        if self.limit > total_size + self.getFileSize(self.user_current_dir):
            self.send_response(301,request,addr)
            while received_size < total_size:
                if total_size - received_size < 8192:  # last recv
                    data = request.recv(total_size - received_size)
                else:
                    data = request.recv(8192)
                received_size += len(data)
                f.write(data)
                print(received_size, total_size)
            else:
                print('file %s recv done' % local_file)
                f.close()
        else:
            print("文件超过限制")
            self.send_response(303,request,addr)

    def _re_get(self,data,):
        """re-send file to client
        1. 拼接文件路径
        2. 判断文件是否存在
            2.1 如果存在，判断文件大小是否与客户端发过来的一致
                2.1.1 如果不一致，返回错误消息
                2.1.2 如果一致，告诉客户端，准备续传吧
                2.1.3 打开文件，Seek到指定位置，循环发送
            2.2 文件不存在，返回错误


        """
        request = self.q.get()
        addr = self.q.get()
        print("_re_get",data)
        abs_filename = data.get('abs_filename')
        full_path = os.path.join(self.user_obj['home'],abs_filename.strip("\\"))
        print("reget fullpath", full_path)
        print("user home",self.user_obj['home'])
        if os.path.isfile(full_path): #2.1
            if os.path.getsize(full_path) == data.get('file_size'):#2.1.2
                self.send_response(401,request,addr)
                f = open(full_path,'rb')
                f.seek(data.get("received_size"))
                for line in f:
                    request.send(line)
                else:
                    print("-----file re-send done------")
                    f.close()
            else:#2.1.1
                self.send_response(402,request,addr,file_size_on_server=os.path.getsize(full_path))
        else:
            self.send_response(300,request,addr)

    @staticmethod
    def getFileSize(filePath, size=0):
        for root, dirs, files in os.walk(filePath):
            for f in files:
                size += os.path.getsize(os.path.join(root, f))
                print(f)
        return size