﻿#!/bin/usr/env python
# -*- coding: utf-8 -*-

import queue
import time
import threading
import socket
from cmppdefines import CMPP_CONNECT_RESP, CMPP_SUBMIT_RESP, CMPP_DELIVER, CMPP_TERMINATE_RESP, CMPP_QUERY_RESP, CMPP_ACTIVE_TEST, CMPP_ACTIVE_TEST_RESP

groupsend = True
send_list = []
recv_list = []
lastheartbeat = True

class resendbox(threading.Thread):

    def __init__(self, terminate, send_queue, interval = 1, T = 60, N = 3):
        threading.Thread.__init__(self)
        self.__resend_box = []
        self.__send_queue = send_queue
        self.__terminate = terminate
        self.__interval = interval
        self.__T = T
        self.__N = N - 1
        self.__count = 0
        self.__thread_stop = False

    def run(self):
        global send_list
        while not self.__thread_stop:
            self.__count += 1

            for resend in self.__resend_box:
                if resend['seq'] in send_list:
                    if (self.__count - resend['count']) > self.__T:
                        if resend['N'] == 0:
                            self.__terminate()
                        else:
                            send_list.remove(resend['seq'])
                            self.__send_queue.put((resend['msg'],resend['seq']))
                            resend['N'] -= 1
                            resend['count'] = self.__count
                else:
                    self.__resend_box.remove(resend)

            if self.__count >= 604800:
                for resend in self.__resend_box:
                    sec = self.__count - resend['count']
                    resend['count'] = self.__T - sec
                self.__count = self.__T

            #print("resendbox",self.__resend_box)
            time.sleep(self.__interval)

    def append(self,seq, msg):
        self.__resend_box.append({'seq': seq,
            'msg': msg, 'count': self.__count, 'N': self.__N})

    def stop(self):
        self.__thread_stop = True

class scavenger(threading.Thread):

    def __init__(self, interval = 0.5):
        threading.Thread.__init__(self)
        self.__interval = interval
        self.__thread_stop = False

    def run(self):
        global send_list
        global recv_list
        while not self.__thread_stop:

            for sid in recv_list:
                if sid in send_list:
                    send_list.remove(sid)

            #print(self.__resend_box)
            time.sleep(self.__interval)
        return

    def stop(self):
        self.__thread_stop = True

class heartbeat(threading.Thread):

    def __init__(self, active, C=30):
        threading.Thread.__init__(self)
        self.__thread_stop = False
        self.__active = active
        self.__C = C

    def run(self):
        global lastheartbeat
        print('contact thread start')
        count = 0
        while not self.__thread_stop:
            if count < self.__C:
                if lastheartbeat == True:
                    lastheartbeat = False
                    count = 0
                else:
                    count += 1
            else:
                self.__active()
                count = 0
                lastheartbeat = False
            time.sleep(1)
#            print('idle:%d' % count)

    def stop(self):
        self.__thread_stop = True

class recvthread(threading.Thread):

    def __init__(self, recv, deliverresp, activeresp, recv_queue, interval = 0):
        threading.Thread.__init__(self)
        self.__recv = recv
        self.__recv_queue = recv_queue
        self.__deliverresp = deliverresp
        self.__activeresp = activeresp
        self.__interval = interval
        self.__thread_stop = False

    def run(self):
        global recv_list
        print('recv thread start')
        while not self.__thread_stop:
            try:
                h,b = self.__recv()
                print(h,b)
                if h['command_id'] in (CMPP_CONNECT_RESP, CMPP_SUBMIT_RESP, CMPP_QUERY_RESP, CMPP_ACTIVE_TEST_RESP, CMPP_TERMINATE_RESP):
                    recv_list.append(h['sequence_id'])
                elif h['command_id'] == CMPP_DELIVER:
                    self.__deliverresp(b['Msg_Id'], 0, h['sequence_id'])
                    recv_list.append(h['sequence_id'])
                    self.__recv_queue.put(b)
                elif h['command_id'] == CMPP_ACTIVE_TEST:
                    self.__activeresp(h['sequence_id'])
                    recv_list.append(h['sequence_id'])
                else:
                    print('unknown command : %d' % h['command_id'])

            except socket.error as arg:
                time.sleep(5)
            time.sleep(self.__interval)

    def stop(self):
        self.__thread_stop = True


class sendthread(threading.Thread):

    def __init__(self, send, terminate, active, send_queue, interval = 0, rate = 15, C=40, T=60, N=3):
        threading.Thread.__init__(self)
        self.__interval = interval
        self.__send = send
        self.__send_queue = send_queue
        self.__grouplength = rate
        self.__heartbeat = heartbeat(active, C)
        self.__scavenger = scavenger()
        self.__resendbox = resendbox(terminate, send_queue, 1, T, N)
        self.__thread_stop = False

    def run(self):
        global send_list
        global groupsend
        global lastheartbeat
        print('send thread start')
        self.__resendbox.setDaemon(True)
        self.__scavenger.setDaemon(True)
        self.__heartbeat.setDaemon(True)
        self.__resendbox.start()
        self.__scavenger.start()
        self.__heartbeat.start()
        while not self.__thread_stop:
            try:
                if len(send_list) < self.__grouplength and groupsend:
                    msg,seq = self.__send_queue.get()
                    if type(msg) == type([]):
                        for index in range(0,len(msg)):
                            self.__send(msg[index])
                    else:
                        self.__send(msg)
                    lastheartbeat = True
                    send_list.append(seq)
                    self.__resendbox.append(seq, msg)

                    print(send_list)
                else:
                    if len(send_list) > 0:
                        groupsend = False
                    else:
                        groupsend = True
                        time.sleep(self.__interval)

            except socket.error as arg:
                print(arg)
                time.sleep(1)

    def stop(self):
        self.__scavenger.stop()
        self.__resendbox.stop()
        self.__heartbeat.stop()
        self.__thread_stop = True



