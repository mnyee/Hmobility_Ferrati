import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile
from rclpy.qos import QoSHistoryPolicy
from rclpy.qos import QoSDurabilityPolicy
from rclpy.qos import QoSReliabilityPolicy

from std_msgs.msg import String, Bool
from interfaces_pkg.msg import LaneInfo, DetectionArray, MotionCommand
from .lib import decision_making_func_lib as DMFL


# 변수 설정
SUB_DETECTION_TOPIC_NAME = "detections"
SUB_LANE_TOPIC_NAME = "yolov8_lane_info"
SUB_TRAFFIC_LIGHT_TOPIC_NAME = "yolov8_traffic_light_info"
SUB_LIDAR_OBSTACLE_TOPIC_NAME = "lidar_obstacle_info"
PUB_TOPIC_NAME = "topic_control_signal"

# 모션 플랜 발행 주기 (초) - 소수점 필요 (int형은 반영되지 않음)
TIMER = 0.1

class MotionPlanningNode(Node):
    def __init__(self):
        super().__init__('motion_planner_node')

        # 토픽 이름 설정
        self.sub_detection_topic = self.declare_parameter('sub_detection_topic', SUB_DETECTION_TOPIC_NAME).value
        self.sub_lane_topic = self.declare_parameter('sub_lane_topic', SUB_LANE_TOPIC_NAME).value
        self.sub_traffic_light_topic = self.declare_parameter('sub_traffic_light_topic', SUB_TRAFFIC_LIGHT_TOPIC_NAME).value
        self.sub_lidar_obstacle_topic = self.declare_parameter('sub_lidar_obstacle_topic', SUB_LIDAR_OBSTACLE_TOPIC_NAME).value
        self.pub_topic = self.declare_parameter('pub_topic', PUB_TOPIC_NAME).value
        
        self.timer_period = self.declare_parameter('timer', TIMER).value

        # QoS 설정
        self.qos_profile = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            history=QoSHistoryPolicy.KEEP_LAST,
            durability=QoSDurabilityPolicy.VOLATILE,
            depth=1
        )

        # 변수 초기화
        self.detection_data = None
        self.lane_data = None
        self.traffic_light_data = None
        self.lidar_data = None

        self.steering_command = 0
        self.left_speed_command = 0
        self.right_speed_command = 0
        

        # 서브스크라이버 설정
        self.detection_sub = self.create_subscription(DetectionArray, self.sub_detection_topic, self.detection_callback, self.qos_profile)
        self.lane_sub = self.create_subscription(LaneInfo, self.sub_lane_topic, self.lane_callback, self.qos_profile)
        self.traffic_light_sub = self.create_subscription(String, self.sub_traffic_light_topic, self.traffic_light_callback, self.qos_profile)
        self.lidar_sub = self.create_subscription(Bool, self.sub_lidar_obstacle_topic, self.lidar_callback, self.qos_profile)

        # 퍼블리셔 설정
        self.publisher = self.create_publisher(MotionCommand, self.pub_topic, self.qos_profile)

        # 타이머 설정
        self.timer = self.create_timer(self.timer_period, self.timer_callback)

    def detection_callback(self, msg: DetectionArray):
        self.detection_data = msg

    def lane_callback(self, msg: LaneInfo):
        self.lane_data = msg

    def traffic_light_callback(self, msg: String):
        self.traffic_light_data = msg

    def lidar_callback(self, msg: Bool):
        self.lidar_data = msg
        
    def timer_callback(self):

        if self.lidar_data is not None and self.lidar_data.data is True:
            # 라이다가 장애물을 감지한 경우
            self.steering_command = 0 
            self.left_speed_command = 0 
            self.right_speed_command = 0 

        elif self.traffic_light_data is not None and self.traffic_light_data.data == 'Red':
            # 빨간색 신호등을 감지한 경우
            for detection in self.detection_data.detections:
                if detection.class_name=='traffic_light':
                    x_min = int(detection.bbox.center.position.x - detection.bbox.size.x / 2) # bbox의 좌측상단 꼭짓점 x좌표
                    x_max = int(detection.bbox.center.position.x + detection.bbox.size.x / 2) # bbox의 우측하단 꼭짓점 x좌표
                    y_min = int(detection.bbox.center.position.y - detection.bbox.size.y / 2) # bbox의 좌측상단 꼭짓점 y좌표
                    y_max = int(detection.bbox.center.position.y + detection.bbox.size.y / 2) # bbox의 우측하단 꼭짓점 y좌표

                    if y_max < 140:
                        # 신호등 위치에 따른 정지명령 결정
                        self.steering_command = 0 
                        self.left_speed_command = 0 
                        self.right_speed_command = 0
        else:
            if self.lane_data is None:
                self.steering_command = 0
            else:    
                target_point = (self.lane_data.target_x, self.lane_data.target_y) # 차선의 중심점
                car_center_point = (320, 179) # roi가 잘린 후 차량 앞 범퍼 중앙 위치 320.179

                target_slope = DMFL.calculate_slope_between_points(target_point, car_center_point)
                
                self.get_logger().info(f'Target Slope: {target_slope}') #슬로프 각도 추출코드
                 
                if target_slope > 0 and target_slope <= 10:
                    self.steering_command = 0
                elif target_slope > 10 and target_slope <= 20:
                    self.steering_command = 0
                elif target_slope > 20 and target_slope <= 30:
                    self.steering_command = 1
                elif target_slope > 30 and target_slope <= 40:
                    self.steering_command = 2
                elif target_slope > 40 and target_slope <= 50:
                    self.steering_command = 4
                elif target_slope > 50 and target_slope <= 60:
                    self.steering_command = 5
                elif target_slope > 60 and target_slope <= 70:
                    self.steering_command = 6
                elif target_slope < 0 and target_slope >= -10:
                    self.steering_command = -1
                elif target_slope < -10 and target_slope >= -20:
                    self.steering_command = -2
                elif target_slope < -20 and target_slope >= -30:
                    self.steering_command = -3
                elif target_slope < -30 and target_slope >= -40:
                    self.steering_command = -5
                elif target_slope < -40 and target_slope >= -50:
                    self.steering_command = -7
                elif target_slope < -50 and target_slope >= -60:
                    self.steering_command = -7
                elif target_slope < -60 and target_slope >= -70:
                    self.steering_command = -7
                else:
                    self.steering_command = 0  
                
            self.left_speed_command = 255  # 예시 속도 값
            self.right_speed_command = 255  # 예시 속도 값
            
                #하던거
                #  if target_slope > 0 and target_slope <= 10:
                #     self.steering_command = 0
                # elif target_slope > 10 and target_slope <= 20:
                #     self.steering_command = 1
                # elif target_slope > 20 and target_slope <= 30:
                #     self.steering_command = 2
                # elif target_slope > 30 and target_slope <= 40:
                #     self.steering_command = 3
                # elif target_slope > 40 and target_slope <= 50:
                #     self.steering_command = 4
                # elif target_slope > 50 and target_slope <= 60:
                #     self.steering_command = 5
                # elif target_slope > 60 and target_slope <= 70:
                #     self.steering_command = 6
                # elif target_slope < 0 and target_slope >= -10:
                #     self.steering_command = -1
                # elif target_slope < -10 and target_slope >= -20:
                #     self.steering_command = -2
                # elif target_slope < -20 and target_slope >= -30:
                #     self.steering_command = -3
                # elif target_slope < -30 and target_slope >= -40:
                #     self.steering_command = -4
                # elif target_slope < -40 and target_slope >= -50:
                #     self.steering_command = -7
                # elif target_slope < -50 and target_slope >= -60:
                #     self.steering_command = -7
                # elif target_slope < -60 and target_slope >= -70:
                #     self.steering_command = -7
                # else:
                #     self.steering_command = 0
            
            # self.left_speed_command = 100  # 예시 속도 값
            # self.right_speed_command = 100  # 예시 속도 값
                #여기까지
            
                # if target_slope > 0:
                #     self.steering_command =  7 # 예시 속도 값 (7이 최대 조향) 
                # elif target_slope < 0:
                #     self.steering_command =  -7
                # else:
                #     self.steering_command = 0
                
                
                # if self.lane_data.slope > 0:
                #    self.steering_command =  7
                # elif self.lane_data.slope < 0:
                #    self.steering_command =  -7
                # else:
                #    self.steering_command = 0
                

        self.get_logger().info(f'Steering Command: {self.steering_command}') #조향값 추출

        # 모션 명령 메시지 생성 및 퍼블리시
        motion_command_msg = MotionCommand()
        motion_command_msg.steering = self.steering_command
        motion_command_msg.left_speed = self.left_speed_command
        motion_command_msg.right_speed = self.right_speed_command
        self.publisher.publish(motion_command_msg)

def main(args=None):
    rclpy.init(args=args)
    node = MotionPlanningNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        print("\n\nshutdown\n\n")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
