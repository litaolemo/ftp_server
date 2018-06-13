from core import main


class ManagementTool(object):
    """负责对用户输入的指令进行解析并调用相应模块处理"""
    def __init__(self,sys_argv):
        self.sys_argv = sys_argv
        #print(self.sys_argv)

    def verify_argv(self):
        """验证指令合法性"""
        if len(self.sys_argv) < 2:
            self.help_msg()
        cmd = self.sys_argv[1]
        #print(cmd)
        if not hasattr(self,cmd):
            print("invalid argument")
            self.help_msg()
        else:
            self.execute()

    def execute(self):
        """解析并执行指令"""
        print('------------')
        cmd = self.sys_argv[1]
        func = getattr(self,cmd)
        func()

    def start(self):
        """start FTP"""
        print("启动FTP")
        server = main.Ftpserver(self)
        server.run_forever()


    def help_msg(self):
        msg = """
        start       start FTP
        stop        stop FTP
        restart     restart FTP
        createuser  username    create a ftp user
        
        """
        print(msg)