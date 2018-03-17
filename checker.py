import psutil
import time
import re
import os
import shutil
import sys
import shlex
import configparser
import config
from status import Status

#[[$SRC_FILES...]] usage examples:
#[[$SRC_FILES...]]         --> a.cppb.cppc.cpp
#[[$SRC_FILES... ]]        --> a.cpp b.cpp c.cpp
#[[$SRC_FILES... –r, ]]    --> a.cpp –r, b.cpp –r, c.cpp –r,
#[[$SRC_FILES_TAIL... ]]   --> b.cpp c.cpp
#[[$SRC_FILES_RTAIL... ]]  --> a.cpp b.cpp
#[[$SRC_FILES_HEAD]]       --> a.cpp
#[[$SRC_FILES_RHEAD]]      --> c.cpp

COMPILE_COMMANDS = {
    'C++' : 'g++ [[$SRC_FILES... ]] -o [[$TARGET_PATH]] -std=c++14 -O2',
    'C'   : 'gcc [[$SRC_FILES... ]] -o [[$TARGET_PATH]] -std=c11 -O2',
    'C#'  : 'mcs [[$SRC_FILES... ]] -out:[[$TARGET_PATH]] -optimize',
}

EXTENSIONS = {
    'C++' : ('.cpp', '.hpp', '.cxx', '.hxx', '.c', '.h', ),
    'C'   : ('.c', '.h'),
    'C#'  : ('.cs'),
}

RUN_COMMANDS = {
    'C++' : '[[$TARGET_PATH]]',
    'C'   : '[[$TARGET_PATH]]',
    'C#'  : '[[$TARGET_PATH]]',
}

APPARMOR_PROFILES = {
    'C++' : '''
#include <tunables/global>
[[$TARGET_PATH]] {
    #include <abstractions/base>
    [[$TARGET_PATH]] mr,
}
''',

    'C' : '''
#include <tunables/global>
[[$TARGET_PATH]] {
    #include <abstractions/base>
    [[$TARGET_PATH]] mr,
}
''',

    'C#' : '''
#include <tunables/global>
[[$TARGET_PATH]] {
    #include <abstractions/base>
    /etc/mono/config r,
    /usr/bin/mono-sgen mrix,
    /usr/lib{,32,64}/** mrix,
    /var/lib/binfmts/ r,
    /var/lib/binfmts/** r,
    [[$TARGET_PATH]] mr,
}
''',
}

class Checker:
    def __init__(self, language, solution_dir, task_dir, temp_dir):
        self.language = language
        self.solution_dir = solution_dir
        self.task_dir = task_dir
        self.temp_dir = temp_dir
        self.solution_files = []
        for file in os.listdir(solution_dir):
            if file.endswith(EXTENSIONS[language]):
                self.solution_files.append(solution_dir + '/' + file)
        self.target = os.path.abspath(temp_dir + '/target')
        config = configparser.ConfigParser()
        config.read(task_dir + '/task_info.ini')
        self.memory_limit = float(config[language]['memory'])
        self.time_limit = float(config[language]['time'])
        self.failed_test_num = -1

    def get_elements(self, cmd, varname):
        regex = '{0}.*?{1}.*?{2}'.format(re.escape('[['), re.escape(varname), re.escape(']]'))
        return re.findall(regex, cmd, re.DOTALL)

    def replace_single(self, cmd, varname, repl=None):
        elements = self.get_elements(cmd, varname)
        for e in elements:
            try:
                replacement = e.replace(varname, repl)[2:-2]
            except:
                replacement = ''
            cmd = cmd.replace(e, replacement)
        return cmd

    def replace_multiple(self, cmd, varname, repl=None):
        elements = self.get_elements(cmd, varname)
        for e in elements:
            replacement = ''
            try:
                for file in repl:
                    replacement += e.replace(varname, file)[2:-2]
            except:
                replacement = ''
            cmd = cmd.replace(e, replacement)
        return cmd

    def replace_vars(self, cmd):
        if len(self.solution_files) > 1:
            cmd = self.replace_multiple(cmd, '$SRC_FILES_TAIL...', self.solution_files[1:])
            cmd = self.replace_multiple(cmd, '$SRC_FILES_RTAIL...', self.solution_files[:-1])
        else:
            cmd = self.replace_multiple(cmd, '$SRC_FILES_TAIL...')
            cmd = self.replace_multiple(cmd, '$SRC_FILES_RTAIL...')
        if len(self.solution_files) > 0:
            cmd = self.replace_multiple(cmd, '$SRC_FILES...', self.solution_files)
            cmd = self.replace_single(cmd, '$SRC_FILES_HEAD', self.solution_files[0])
            cmd = self.replace_single(cmd, '$SRC_FILES_RHEAD', self.solution_files[-1])
        else:
            cmd = self.replace_multiple(cmd, '$SRC_FILES...')
            cmd = self.replace_single(cmd, '$SRC_FILES_HEAD')
            cmd = self.replace_single(cmd, '$SRC_FILES_RHEAD')
        cmd = self.replace_single(cmd, '$TARGET_PATH', self.target)
        return cmd

    def compile_solution(self):
        cmd = self.replace_vars(COMPILE_COMMANDS[self.language])
        with open(self.temp_dir + '/compiler_output', 'w') as outfile:
            process = psutil.Popen(shlex.split(cmd), stdout=outfile, stderr=outfile)
            try:
                code = process.wait(timeout=config.COMPILATION_TIME_LIMIT)
                if code != 0:
                    outfile.close()
                    return Status.COMPILATION_ERROR
                outfile.close()
                return Status.OK
            except psutil.TimeoutExpired:
                outfile.close()
                return Status.COMPILATION_TIME_LIMIT_EXCEEDED

    def create_apparmor_profile(self):
        devnull = open(os.devnull, 'w')
        cmd = 'sudo aa-disable {0}'.format(self.target)
        process = psutil.Popen(shlex.split(cmd), stdout=devnull, stderr=devnull)
        process.wait(timeout=30)
        profile_name = self.target.replace('/', '.')[1:]
        profile_path = '/etc/apparmor.d/' + profile_name
        profile = self.replace_vars(APPARMOR_PROFILES[self.language])
        file = open(profile_path, 'w')
        file.write(profile)
        file.close()
        cmd = 'sudo aa-enforce {0}'.format(self.target)
        process = psutil.Popen(shlex.split(cmd), stdout=devnull, stderr=devnull)
        code = process.wait(timeout=30)
        if code != 0:
            raise Exception('Unable to enforce apparmor profile.')

    def run_target(self, input_path):
        time_limit_exceeded = False
        mem_limit_exceeded = False
        output_path = self.temp_dir + '/output'
        stderr_path = self.temp_dir + '/stderr'
        name, ext = os.path.splitext(input_path)
        etalon_path = name + '.out'
        with open(output_path, 'w') as output_file, open(input_path, 'r') as input_file, open(stderr_path, 'w') as stderr_file:
            cmd = self.replace_vars(RUN_COMMANDS[self.language])
            process = psutil.Popen(shlex.split(cmd), stdout=output_file, stdin=input_file, stderr=stderr_file)
            start_time = time.time()
            step = 0.001
            code = -1
            while time.time() - start_time < self.time_limit:
                try:
                    mem_used = process.memory_info().rss / 1024 / 1024
                    if mem_used > self.memory_limit:
                        mem_limit_exceeded = True
                        break
                    code = process.wait(timeout=step)
                    break
                except psutil.TimeoutExpired:
                    continue
            if process.is_running() and not mem_limit_exceeded:
                time_limit_exceeded = True
            if time_limit_exceeded:
                process.kill()
                return Status.TIME_LIMIT_EXCEEDED
            elif mem_limit_exceeded:
                process.kill()
                return Status.MEMORY_LIMIT_EXCEEDED
            else:
                if code == -11:
                    return Status.SECURITY_VIOLATION_ERROR
                elif code != 0:
                    return Status.RUNTIME_ERROR
                else:
                    output_file.close()
                    output_file = open(output_path, 'r')
                    etalon_file = open(etalon_path, 'r')
                    output = output_file.readlines()
                    etalon = etalon_file.readlines()
                    output_file.close()
                    etalon_file.close()
                    if len(output) != len(etalon):
                        return Status.WRONG_ANSWER
                    output[-1] = output[-1].rstrip()
                    etalon[-1] = etalon[-1].rstrip()
                    if output == etalon:
                        return Status.OK
                    else:
                        return Status.WRONG_ANSWER

    def get_failed_test_num(self):
        return self.failed_test_num

    def get_stderr(self):
        try:
            file = open(self.temp_dir + '/stderr', 'r')
            stderr = file.read()
            file.close()
            return stderr
        except:
            return ''

    def get_compiler_output(self):
        try:
            file = open(self.temp_dir + '/compiler_output', 'r')
            compiler_output = file.read()
            file.close()
            return compiler_output
        except:
            return ''

    def check(self):
        if os.getuid() != 0:
            print('You should run checker with sudo privileges!')
            sys.exit(1)
        shutil.rmtree(self.temp_dir)
        os.mkdir(self.temp_dir)
        compilation_result = self.compile_solution()
        if compilation_result != Status.OK:
            return compilation_result
        self.create_apparmor_profile()
        i = 1
        for file in os.listdir(self.task_dir):
            if file.endswith('.in'):
                res = self.run_target(self.task_dir + '/' + file)
                if res != Status.OK:
                    self.failed_test_num = i
                    return res
                i += 1
        return Status.OK
