import optparse
from socket import *
import json
import os
import shelve


class FtpClient (object):
    """ftp客户端"""
    MSG_SIZE = 1024  # 消息最长1024

    def __init__(self):
        self.sock = socket(AF_INET, SOCK_STREAM)
        self.username = None
        self.terminal_display = None
        self.shelve_obj = shelve.open("db")
        parser = optparse.OptionParser()
        parser.add_option("-s", "--server", dest="server", help="ftp server ip_addr")
        parser.add_option("-P", "--port", type="int", dest="port", help="ftp server port")
        parser.add_option("-u", "--username", dest="username", help="username info")
        parser.add_option("-p", "--password", dest="password", help="password info")
        #self.options, self.args = parser.parse_args()
        self.options = {'server': 'localhost', 'port': 9999, 'username': None, 'password': None}
        self.args = []
        #print(self.options,self.args,type(self.options),self.options.server)
        self.argv_verification()

        self.make_connection()

    def argv_verification(self):
        """检查合法性"""
        if not self.options["server"] or not self.options["port"]:
            exit("Error: must supply server and port parameters")

    def make_connection(self):
        """建立socket连接"""
        print((self.options["server"], self.options["port"]))
        self.sock.connect((self.options["server"], self.options["port"]))

    def auth(self):
        """用户认证"""
        count = 0
        while count < 3:
            username = input("用户名").strip()
            if not username:continue
            password = input("密码").strip()
            cmd = {
                'action_type': 'auth',
                'username': username,
                'password': password,
            }
            self.sock.send(json.dumps(cmd).encode("utf-8"))
            response = self.get_response()
            print("response",response)
            if response.get('status_code') == 200:
                self.username = username
                self.terminal_display = "[%s]" % self.username
                self.current_dir = "\\"
                return True
            else:
                print(response['status_msg'])
            count += 1

    def unfubusged_file_check(self):
        "检查shelve db ，把未正常传完的文件打印，按用户指令决定是否重新传输"
        if list(self.shelve_obj.keys()):
            print("-------Unfinished file list -------------")
            for index, abs_file in enumerate(self.shelve_obj.keys ()):
                received_file_size = os.path.getsize(self.shelve_obj[abs_file][1])
                print("%s. %s    %s    %s   %s" % (index, abs_file,
                                                    self.shelve_obj[abs_file][0],
                                                    received_file_size,
                                                    received_file_size / self.shelve_obj[abs_file][0] * 100
                                                    ))

            while True:
                choice = input("[select file index to re-download]").strip()
                if not choice: continue
                if choice == 'back': break
                if choice.isdigit():
                    choice = int(choice)
                    if choice >= 0 and choice <= index:
                        selected_file = list(self.shelve_obj.keys())[choice]
                        already_received_size = os.path.getsize(self.shelve_obj[selected_file][1])

                        print ("tell server to resend file ", selected_file)
                        # abs_filename + size +received_size
                        self.send_msg('re_get', file_size=self.shelve_obj[selected_file][0],
                                       received_size=already_received_size,
                                       abs_filename=selected_file)
                        response = self.get_response ()
                        if response.get('status_code') == 401:  # "File exist ,ready to re-send !",
                            local_filename = self.shelve_obj[selected_file][1]

                            f = open(local_filename, 'ab')
                            total_size = self.shelve_obj[selected_file][0]
                            recv_size = already_received_size
                            current_percent = int(recv_size / total_size * 100)
                            progress_generator = self.progress_bar(total_size, current_percent, current_percent)
                            progress_generator.__next__()
                            while recv_size < total_size:
                                if total_size - recv_size < 8192:  # last recv
                                    data = self.sock.recv(total_size - recv_size)
                                else:
                                    data = self.sock.recv(8192)
                                recv_size += len(data)
                                f.write(data)
                                progress_generator.send(recv_size)
                                # progress_generator.send(received_size)
                                # print(recv_size,total_size)
                            else:
                                print("file re-get done")
                        else:
                            print(response.get("status_msg"))

    def interactive(self):
        """处理Ftpserver的所有交互"""
        if self.auth():
            self.unfubusged_file_check()
            while True:
                user_input = input("%s>>:"%self.terminal_display)
                if not user_input:continue
                cmd_list = user_input.split()
                if hasattr(self,"_%s"%cmd_list[0]):
                    func = getattr(self,"_%s"%cmd_list[0])
                    func(cmd_list[1:])

    def parameter_check(self,args,min_args=None,max_args=None,exact_args=None):
        if min_args:
            if len(args) <min_args:
                print("must provide at least %s parameters but %s received" %(min_args,len(args)))
                return False
        if max_args:
            if len(args) > max_args:
                print ("must provide at most %s parameters but %s received" % (max_args, len(args)))
                return False

        if exact_args:
            if len(args) != exact_args:
                print("need exactly %s parameters but %s received" % (exact_args, len (args)))
                return False
        return True

    def send_msg(self,action_type,**kwargs):
        msg_data = {'action_type': action_type,
                    'username': self.username,
                    'fill': '',
                    }
        msg_data.update(kwargs)
        b_msg = json.dumps(msg_data).encode()
        if self.MSG_SIZE > len(b_msg):
            msg_data['fill'] = msg_data['fill'].zfill(self.MSG_SIZE - len(b_msg))
            b_msg = json.dumps(msg_data).encode()

        self.sock.send(b_msg)

    def _get(self,cmd_args):
        """下载功能
            1.拿到文件名
            2.发送到远程
            3.等待服务器返回消息
                3.1 如果文件存在，拿到文件大小
                    3.1.1循环接收
                3.2 文件不存在
                    print  status_msg
        """
        if self.parameter_check(cmd_args,min_args=1):
            filename = cmd_args[0]
            self.send_msg(action_type='get',filename=filename)
            response = self.get_response()
            if response.get('status_code') == 301:# file exist ,ready to receive
                file_size = response.get('file_size')
                received_size = 0

                progress_generator = self.progress_bar(file_size)
                progress_generator.__next__()

                # save to shelve db
                file_abs_path = os.path.join(self.current_dir,filename)
                self.shelve_obj[file_abs_path] = [file_size,"%s.download" % filename]

                f = open("%s.download" % filename,"wb")
                while received_size < file_size:
                    if file_size - received_size < 8192:#last recv
                        data = self.sock.recv(file_size - received_size)
                    else:
                        data = self.sock.recv(8192)
                    received_size += len(data)
                    f.write(data)
                    progress_generator.send(received_size)

                    #print(received_size,file_size)
                else:
                    print('\n')
                    print("---file [%s] recv done,received size [%s]----"%( filename,file_size))
                    del self.shelve_obj[file_abs_path]
                    f.close()
                    os.rename("%s.download"% filename, filename)

            else:
                print(response.get('status_msg'))


    def get_response(self):
        """获取服务器端返回"""
        data = self.sock.recv(self.MSG_SIZE)
        return json.loads(data.decode("utf-8"))

    def _ls(self,cmd_args):
        """显示文件目录"""
        self.send_msg(action_type='ls')
        response = self.get_response()
        print(response)
        if response.get('status_code') == 302:
            cmd_size = response.get('cmd_result_size')
            received_size = 0
            cmd_result = b''
            while received_size < cmd_size:
                if cmd_size - received_size < 8192:
                    data = self.sock.recv(cmd_size - received_size)
                    #print(data)
                else:
                    data = self.sock.recv(8192)
                cmd_result += data
                received_size += len(data)
            else:
                #print("完成")
                print(cmd_result.decode('gbk'))

    def _cd(self,cmd_args):
        """切换目录"""
        if self.parameter_check(cmd_args,exact_args=1):
            target_dir = cmd_args[0]
            self.send_msg('cd',target_dir=target_dir)
            response = self.get_response()
            print(response)
            if response.get('status_code') == 350:
                self.terminal_display = "[%s]"% response.get('current')
                self._ls(cmd_args)

    def _put(self,cmd_args):
        """上传本地文件到服务器
        1.确保本地文件存在
        2.确定文件名，大小，放到消息头里，发送给远程
        3.打开文件，发送内容
        """
        if self.parameter_check(cmd_args, exact_args=1):
            local_file = cmd_args[0]
            if os.path.isfile(local_file):
                total_size = os.path.getsize(local_file)
                self.send_msg('put',file_size=total_size,filename=local_file)
                f = open(local_file,'rb')
                uploaded_size = 0

                response = self.get_response()
                if response.get ('status_code') == 301:
                    progress_generator = self.progress_bar(total_size)
                    progress_generator.__next__()
                    for line in f:
                        self.sock.send(line)
                        uploaded_size += len(line)
                        progress_generator.send(uploaded_size)

                    else:
                        print('\n')
                        print('file upload done'.center(50,'-'))
                        f.close()
                else:
                    print("超出磁盘余额大小")

    def progress_bar(self,total_size,current_percent=0,last_percent=0):


        while True:
            received_size = yield current_percent
            current_percent = int(received_size / total_size *100)

            if current_percent > last_percent:
                print("#" * int(current_percent / 2) + "{percent}%".format(percent=current_percent), end='\r',
                      flush=True)
                last_percent = current_percent  # 把本次循环的percent赋值给last

if __name__ == "__main__":
    client = FtpClient()
    client.interactive()