import csv
import http.server
import inspect
import io
import json
import os
import socketserver
import subprocess
from http import HTTPStatus

from windows_shortcuts import read_shortcut_path

script_path = os.path.dirname(os.path.abspath(__file__))


def contents(filename):
    with open(filename, "rb") as handle:
        return handle.read()


def deprefix(s, prefix):
    assert s.startswith(prefix)
    return s[len(prefix):]


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            template_dir = os.path.join(script_path, "templates")
            print(self.path)
            self.send_response(HTTPStatus.OK)

            main_page_template_filename = os.path.join(template_dir, "main.html")
            main_page_template = contents(main_page_template_filename).decode("utf-8")

            service_template_filename = os.path.join(template_dir, "service.html")
            service_template = contents(service_template_filename).decode("utf-8")

            services_html_fragments = []
            for i, service_def in enumerate(global_service_defs):

                is_running = service_def.check_running()
                if is_running:
                    status = "Is running"
                else:
                    status = "Is not running"

                service_template_params = {
                    "name": service_def.name,
                    "start_link": "/start/%d" % i,
                    "status": status
                }

                service_html_fragment = service_template % service_template_params
                services_html_fragments.append(service_html_fragment)

            params = {"services": "".join(services_html_fragments)}

            main_page_contents = main_page_template % params

            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(main_page_contents.encode("utf-8"))
        elif self.path.startswith("/start/"):
            argument = int(deprefix(self.path, "/start/"))
            start_process_def = global_service_defs[argument]
            if not start_process_def.check_running():
                start_process_def.start()
            self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
            self.send_header("Location", "/")
            self.end_headers()
        else:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()


def csv_to_dict(csv_text):
    f = io.StringIO(csv_text)
    reader = csv.reader(f)
    out = []
    while True:  # loop until we get a non-blank header line
        header = next(reader)
        if header:
            break
    for row in reader:
        out.append({key: value for (key, value) in zip(header, row)})
    return out


def get_process_details(process_name):
    if process_name is None:
        where_clause = []
    else:
        where_clause = ["where", "name like '%s'" % process_name]
    csv_output = subprocess.check_output(["wmic", "path", "win32_process"] + where_clause + ["get", "caption,processid,commandline", "/format:csv"])
    return csv_to_dict(csv_output.decode("windows-1252"))


def command_line_matcher(expected_command_line, actual_command_line):
    return expected_command_line == actual_command_line


class ServiceDef(object):
    def __init__(self, name, process_exe, target):
        """
        :param name: display name of the service
        :param process_exe: the name of the exe file proper. This is what we look for in the task list
        """
        self.process_exe = process_exe
        self.name = name
        self.target = target

    def check_running(self):
        process_details = get_process_details(self.process_exe)
        # print("process details", process_details)
        expected_command_line = self.get_expected_command_line()
        found = False
        for entry in process_details:
            if command_line_matcher(expected_command_line, entry["CommandLine"]):
                found = True
                break
        return found

    def start(self):
        ext = self.target.rsplit(".", 1)[-1]
        if ext.lower() == "lnk":
            os.startfile(self.target)
        else:
            assert False, "don't know how to handle target of type %s" % ext

    def get_expected_command_line(self):
        ext = self.target.rsplit(".", 1)[-1]
        if ext.lower() == "lnk":
            target_path, additional_data = read_shortcut_path(self.target)
            # print("shortcut path", repr(target_path))

            arguments = additional_data.get("command_line_arguments")
            if arguments is None:
                return target_path
            else:
                return target_path + " " + arguments
        else:
            assert False, "don't know how to handle target of type %s" % ext

def json_contents(filename):
    with open(filename, "rb") as handle:
        return json.load(handle)


def read_objects():
    """:rtype: list of ServiceDef"""
    config_filename = os.path.join(script_path, "summoner.json")

    raw_configs = json_contents(config_filename)

    assert isinstance(raw_configs, list)

    out = []
    for i, raw_config in enumerate(raw_configs):
        try:
            config = ServiceDef(**raw_config)
        except TypeError:
            # If we failed because the config file params don't match give a nicer message
            service_def_params = inspect.getargs(ServiceDef.__init__.__code__).args
            assert service_def_params[0] == "self"
            service_def_params = service_def_params[1:]
            msg = "In service definition #%d, raw config keys %r don't match ServiceDef parameters %r" % (i, list(raw_config.keys()), service_def_params)
            raise Exception(msg)
        out.append(config)
    return out


global_service_defs = None
""":type: list of ServiceDef"""


def main():
    print("loading configuration")
    global global_service_defs
    global_service_defs = read_objects()
    port = 8888
    print("Starting server on port %d" % port)
    httpd = socketserver.TCPServer(('', port), Handler)
    print("Listening at http://localhost:%d" % port)
    httpd.serve_forever()


if __name__ == "__main__":
    main()