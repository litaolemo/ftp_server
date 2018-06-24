import os,sys

Base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(Base_dir)
#print(Base_dir)


if __name__ == "__main__":
    from core import management
    #print("start")
    #argv_parser = management.ManagementTool(sys.argv)
    #print(sys.argv)
    argv_parser = management.ManagementTool(['',"start"])
    argv_parser.verify_argv()