class Status:
    OK                              = 0
    COPYING                         = 1
    WAITING                         = 2
    WRONG_ANSWER                    = 3
    RUNTIME_ERROR                   = 4
    INTERNAL_ERROR                  = 5
    COMPILATION_ERROR               = 6
    TIME_LIMIT_EXCEEDED             = 7
    MEMORY_LIMIT_EXCEEDED           = 8
    SECURITY_VIOLATION_ERROR        = 9
    INVALID_SOLUTION_FORMAT_ERROR   = 10
    INVALID_SOLUTION_FORMAT_WAITING = 11
    COMPILATION_TIME_LIMIT_EXCEEDED = 12

    def get_string(status):
        strings = {
            Status.OK                              : 'Accepted',
            Status.COPYING                         : 'Copying',
            Status.WAITING                         : 'Waiting',
            Status.WRONG_ANSWER                    : 'Wrong Answer',
            Status.RUNTIME_ERROR                   : 'Runtime Error',
            Status.INTERNAL_ERROR                  : 'Internal Error',
            Status.COMPILATION_ERROR               : 'Compilation Error',
            Status.TIME_LIMIT_EXCEEDED             : 'Time Limit Exceeded',
            Status.MEMORY_LIMIT_EXCEEDED           : 'Memory Limit Exceeded',
            Status.SECURITY_VIOLATION_ERROR        : 'Security Violation Error',
            Status.INVALID_SOLUTION_FORMAT_ERROR   : 'Invalid Solution Format Error',
            Status.INVALID_SOLUTION_FORMAT_WAITING : 'Invalid Solution Format Waiting',
            Status.COMPILATION_TIME_LIMIT_EXCEEDED : 'Compilation Time Limit Exceeded',
        }
        return strings[status]
