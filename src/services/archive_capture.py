"""Fresh frame taps for configured archive sources, separate from AI selection."""
import threading
import time
import cv2

class ArchiveCapture:
    def __init__(self,state):self.state=state;self.remote={};self.lock=threading.Lock()
    def __call__(self,source):
        if source==self.state.local_source_id:
            with self.state.lock:return self.state.latest_frame.copy() if self.state.latest_frame is not None and time.time()-self.state.latest_frame_at<3 else None
        with self.lock:
            tap=self.remote.get(source)
            if not tap or not tap['thread'].is_alive():
                tap={'frame':None,'time':0,'requested':time.time()};self.remote[source]=tap
                tap['thread']=threading.Thread(target=self.run,args=(source,tap),daemon=True);tap['thread'].start()
            tap['requested']=time.time()
            return tap['frame'].copy() if tap['frame'] is not None and time.time()-tap['time']<3 else None
    def run(self,source,tap):
        cap=None
        try:
            while time.time()-tap['requested']<5:
                if cap is None:
                    if source not in self.state.sources:return
                    cap=cv2.VideoCapture('rtsp://127.0.0.1:8554/'+source,cv2.CAP_FFMPEG,[cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,2000,cv2.CAP_PROP_READ_TIMEOUT_MSEC,2000])
                ok,frame=cap.read()
                if not ok:
                    cap.release();cap=None;time.sleep(.5);continue
                tap['frame']=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB);tap['time']=time.time()
        finally:
            if cap is not None:cap.release()
