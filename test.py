import cv2
import mediapipe as mp
import math
import time
from datetime import datetime
import numpy as np
import json
from azure.storage.blob import BlobClient, generate_blob_sas, BlobSasPermissions
from dotenv import load_dotenv
import os
import requests

# === USER SETTINGS === 
patient_name = "bob"
camera_id = 1
user_id = 1

# === GLOBAL VARIABLES === #
# keypoint positions
x_nose = 0
y_nose = 0
x_left_shoulder = 0
y_left_shoulder = 0
x_right_shoulder = 0
y_right_shoulder = 0
x_left_hip = 0
y_left_hip = 0
x_right_hip = 0
y_right_hip = 0

previous_y_nose = 1
previous_x_hip = 1
x_average_position = 0

# velocity
current_x_velocity = 0
current_y_velocity = 0

# timestamps
current_timestamp = None
previous_timestamp = time.time()

# video feed
buffer_amount = 100
buffer_array = []
videoTitle = ""

# other
fall_detected = False
threshold_height = 800
threshold_line = "------------------------------------------------------------------------------------------------"
status = "EVERYTHING OK"
movement_counter = 0
frame_counter = 0
data_json = None

load_dotenv()

# === FUNCTIONS === #

# create video
def createVideo(array):
    out = cv2.VideoWriter(f"{videoTitle}", fourcc, 20.0, (1920, 1080))
    for array_frame in array:
        out.write(array_frame)

# send video
account_name = os.getenv("AZURE_STORAGE_ACCOUNT")
account_key = os.getenv("ACCOUNT_KEY")
container_name = os.getenv("AZURE_STORAGE_CONTAINER")

def sendVideo(videoTitle):
    blob_name = f"{videoTitle}"
    blob_client = BlobClient(
        account_url=f"https://{account_name}.blob.core.windows.net",
        container_name=container_name,
        blob_name=blob_name,
        credential=account_key,
    )
    generate_blob_sas(
        account_name=account_name,
        account_key=account_key,
        container_name=container_name,
        blob_name=blob_name,
        permission=BlobSasPermissions(write=True),
        expiry=999,
    )
    with open(f"{videoTitle}", "rb") as data:
        blob_client.upload_blob(data, blob_type="BlockBlob")

# construct alert
def constructJsonAlert(cameraId, triggerTime, videoTitle):
    return json.dumps(
        {
            "cameraId": cameraId,
            "triggerTime": triggerTime,
            "videoData": f"https://sateamelderguardians.blob.core.windows.net/blobelderguardians/{videoTitle}",
            "isManual": False

            
        }
    )

#send alert
def sendAlert():
    data_json = constructJsonAlert(camera_id, current_timestamp, videoTitle)
    try:
        backend_url = "https://elderguardiansbackend.azurewebsites.net/api/alerts"  # Replace with your actual Java backend URL
        headers = {"Content-Type": "application/json"}

        response = requests.post(backend_url, data=data_json, headers=headers)

        if response.status_code == 200:
            print("Alert sent successfully")
        else:
            print(f"Failed to send alert. HTTP Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending alert: {e}")


# construct movement
def constructMovement(cameraId, totalMovement, userId):
    return json.dumps(
        {
            "date": cameraId,
            "totalMovement": totalMovement,
            "used_id": userId
        }
    )

# send movement
def sendMovement():
    pass

# === PROGRAM === #

mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)

cap = cv2.VideoCapture(0)
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out = None

fps_start_time = time.time()
fps_frame_count = 0
fps = 1

while cap.isOpened():
    _, frame = cap.read()
    frame = cv2.resize(frame, (1920, 1080))

    if fall_detected:
        buffer_amount = 200
        if len(buffer_array) >= buffer_amount:
            createVideo(buffer_array)
            sendVideo(videoTitle)
            sendAlert()
            buffer_array = []
            buffer_amount = 100
            fall_detected = False
        else:
            buffer_array.append(frame)

    else:
        if len(buffer_array) >= buffer_amount:
            buffer_array.pop(0)
            buffer_array.append(frame)
        else:
            buffer_array.append(frame)

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pose_results = pose.process(frame_rgb)

    try:
        mp_drawing.draw_landmarks(
            frame, pose_results.pose_landmarks, mp_pose.POSE_CONNECTIONS
        )

        image_height, image_width, _ = frame.shape
        x_nose = (
            pose_results.pose_landmarks.landmark[mp_pose.PoseLandmark.NOSE].x
            * image_width
        )
        y_nose = (
            pose_results.pose_landmarks.landmark[mp_pose.PoseLandmark.NOSE].y
            * image_height
        )
        x_left_shoulder = (
            pose_results.pose_landmarks.landmark[mp_pose.PoseLandmark.LEFT_SHOULDER].x
            * image_width
        )
        y_left_shoulder = (
            pose_results.pose_landmarks.landmark[mp_pose.PoseLandmark.LEFT_SHOULDER].y
            * image_height
        )
        x_right_shoulder = (
            pose_results.pose_landmarks.landmark[mp_pose.PoseLandmark.RIGHT_SHOULDER].x
            * image_width
        )
        y_right_shoulder = (
            pose_results.pose_landmarks.landmark[mp_pose.PoseLandmark.RIGHT_SHOULDER].y
            * image_height
        )
        x_left_hip = (
            pose_results.pose_landmarks.landmark[mp_pose.PoseLandmark.LEFT_HIP].x
            * image_width
        )
        y_left_hip = (
            pose_results.pose_landmarks.landmark[mp_pose.PoseLandmark.LEFT_HIP].y
            * image_height
        )
        x_right_hip = (
            pose_results.pose_landmarks.landmark[mp_pose.PoseLandmark.RIGHT_HIP].x
            * image_width
        )
        y_right_hip = (
            pose_results.pose_landmarks.landmark[mp_pose.PoseLandmark.RIGHT_HIP].y
            * image_height
        )

        y_center_top = (y_left_shoulder + y_right_shoulder) / 2
        y_center_bottom = (y_left_hip + y_right_hip) / 2
        average_height = y_center_bottom - y_center_top
        distanceToLaptop = -(math.log(968) - math.log(average_height)) / -0.314
        threshold_height = 800 - (20 * distanceToLaptop - 20)

        x_center_top = (x_left_shoulder + x_right_shoulder) / 2
        x_center_bottom = (x_left_hip + x_right_hip) / 2
        x_average_position = (x_center_top + x_center_bottom) / 2

        def calculate_instantaneous_velocity(
            previous_position, current_position, previous_time, current_time
        ):
            delta_position = current_position - previous_position
            delta_time = current_time - previous_time

            if delta_time == 0:
                return np.zeros_like(
                    delta_position
                )
            velocity = delta_position / delta_time
            return velocity

        # calculate nose keypoint velocity
        prev_keypoint_position = previous_y_nose
        prev_timestamp = previous_timestamp
        current_keypoint_position = y_nose
        current_timestamp = time.time()

        current_y_velocity = calculate_instantaneous_velocity(
            prev_keypoint_position,
            current_keypoint_position,
            prev_timestamp,
            current_timestamp,
        )

        # calculate hip center keypoint velocity
        prev_keypoint_position = previous_x_hip
        prev_timestamp = previous_timestamp
        current_keypoint_position = x_average_position
        current_timestamp = time.time()

        current_x_velocity = calculate_instantaneous_velocity(
            prev_keypoint_position,
            current_keypoint_position,
            prev_timestamp,
            current_timestamp,
        )

    except:
        pass

    # monitor status
    if -200 < current_y_velocity < 200:
        current_y_velocity = 0
    if y_nose > threshold_height and current_y_velocity > 1000:
        status = "!FALL DETECTED - ALERT SEND!"
        fall_detected = True
        datetime_object = datetime.fromtimestamp(
            math.floor(current_timestamp)
        ).strftime("%Y%m%d-%H%M%S")
        videoTitle = f"{patient_name}-{camera_id}-{datetime_object}.mp4"
        data_json = constructJsonAlert(camera_id, datetime_object, videoTitle)
    if status == "!FALL DETECTED - ALERT SEND!" and y_nose < threshold_height:
        status = "RECOVERED FROM FALL"
        fall_detected = False
        buffer_array = []
        buffer_amount = 100

    if -100 < current_x_velocity < 100:
        current_x_velocity = 0
    if current_x_velocity != 0 and x_average_position != previous_x_hip:
        movement_counter += 1

    if y_nose == previous_y_nose and current_y_velocity != 0:  # adjust sensitivity
        status = "!OCCLUDED FALL DETECTED!"

    if status == "!OCCLUDED FALL DETECTED!" and y_nose != previous_y_nose:
        status = "RECOVERED FROM OCCLUDED FALL"

    # calculate fps (use for correcting movement tracking count)
    fps_frame_count += 1
    if time.time() - fps_start_time >= 1:
        fps = fps_frame_count / (time.time() - fps_start_time)
        fps_start_time = time.time()
        fps_frame_count = 0

    # show status in top left corner
    cv2.putText(
        frame,
        f"{data_json}",
        (20, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (255, 255, 255),
        5,
    )

    # show length of buffer array
    cv2.putText(
        frame,
        f"BufLen: {len(buffer_array)}",
        (20, 200),
        cv2.FONT_HERSHEY_SIMPLEX,
        2,
        (255, 255, 255),
        5,
    )

    # show fps
    cv2.putText(
        frame,
        f"FPS: {math.floor(fps)}",
        (20, 300),
        cv2.FONT_HERSHEY_SIMPLEX,
        2,
        (0, 255, 0),
        5,
    )

    # movement time in sec
    cv2.putText(
        frame,
        f"Time moving: {math.floor(movement_counter / 30)} s",
        (20, 400),
        cv2.FONT_HERSHEY_SIMPLEX,
        2,
        (0, 0, 255),
        5,
    )

    # draw threshold line
    cv2.putText(
        frame,
        threshold_line,
        (0, round(threshold_height)),
        cv2.FONT_HERSHEY_SIMPLEX,
        2,
        (0, 255, 0),
        2,
    )

    # output frame to show video
    cv2.imshow("Output", frame)

    # update previous variables
    previous_y_nose = y_nose
    previous_x_hip = x_average_position
    previous_timestamp = current_timestamp
    previous_frame_counter = frame_counter
    frame_counter += 1

    # cancel program on q pressed
    if cv2.waitKey(1) == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
