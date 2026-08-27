"""
Flask API 테스트 스크립트
이미지 파일을 사용하여 이상 탐지 API를 테스트하고 오버레이 이미지 생성 여부를 확인합니다.
"""
import requests
import json
import os
from pathlib import Path

# 테스트 설정
API_BASE_URL = "http://localhost:5000"
# 백엔드 ImageStorageUtil이 반환하는 형식: "images/1/original/view1_frontal.jpg"
# 또는 "Back-End/BitComputer/images/1/original/view1_frontal.jpg"
TEST_IMAGE_PATH = "Back-End/BitComputer/images/1/original/view1_frontal.jpg"

def test_health_check():
    """헬스 체크 엔드포인트 테스트"""
    print("=" * 60)
    print("1. 헬스 체크 테스트")
    print("=" * 60)
    
    try:
        response = requests.get(f"{API_BASE_URL}/api/ai/is_running", timeout=5)
        print(f"상태 코드: {response.status_code}")
        print(f"응답: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code == 200:
            print("✅ 헬스 체크 성공!\n")
            return True
        else:
            print(f"❌ 헬스 체크 실패: {response.status_code}\n")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.\n")
        return False
    except Exception as e:
        print(f"❌ 오류 발생: {e}\n")
        return False

def test_anomaly_detection():
    """이상 탐지 API 테스트"""
    print("=" * 60)
    print("2. 이상 탐지 API 테스트")
    print("=" * 60)
    
    # 테스트 요청 데이터
    test_data = {
        "radiologyRequestId": 1,
        "patientId": 123,
        "employeeId": 456,
        "deptId": 789,
        "symptomDetail": "테스트 증상",
        "memo": "테스트 메모",
        "entryDate": "2024-01-01",
        "detailImageAddress": TEST_IMAGE_PATH
    }
    
    print(f"요청 데이터:")
    print(json.dumps(test_data, indent=2, ensure_ascii=False))
    print()
    
    try:
        # API 호출
        print("API 요청 전송 중...")
        response = requests.post(
            f"{API_BASE_URL}/api/ai/radiology_report",
            json=test_data,
            headers={"Content-Type": "application/json"},
            timeout=60  # 이미지 처리에 시간이 걸릴 수 있음
        )
        
        print(f"상태 코드: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n✅ API 호출 성공!")
            print("\n응답 데이터:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
            # 결과 확인
            print("\n" + "-" * 60)
            print("결과 분석:")
            print("-" * 60)
            print(f"  - Radiology Request ID: {result.get('radiologyRequestId')}")
            print(f"  - Patient ID: {result.get('patientId')}")
            print(f"  - 이상 탐지 결과: {'의심 (True)' if result.get('result') else '정상 (False)'}")
            print(f"  - Anomaly Score: {result.get('result')}")
            print(f"  - Overlay 이미지 경로: {result.get('imageUrl')}")
            
            # Overlay 이미지 파일 확인
            overlay_path = result.get('imageUrl')
            if overlay_path:
                # 프로젝트 루트 기준으로 절대 경로 생성
                project_root = Path(__file__).parent.parent
                # overlay_path는 이미 "images/..." 형식이므로 그대로 사용
                full_overlay_path = project_root / overlay_path
                
                print("\n" + "-" * 60)
                print("Overlay 이미지 확인:")
                print("-" * 60)
                print(f"  - 상대 경로: {overlay_path}")
                print(f"  - 절대 경로: {full_overlay_path}")
                
                if full_overlay_path.exists():
                    file_size = full_overlay_path.stat().st_size
                    print(f"  - ✅ 파일 존재: {full_overlay_path}")
                    print(f"  - 파일 크기: {file_size:,} bytes ({file_size / 1024:.2f} KB)")
                else:
                    print(f"  - ❌ 파일이 존재하지 않습니다: {full_overlay_path}")
            
            return True
        else:
            print(f"\n❌ API 호출 실패: {response.status_code}")
            try:
                error_data = response.json()
                print(f"오류 메시지: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
            except:
                print(f"응답 내용: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ 요청 시간 초과 (60초)")
        print("   이미지 처리에 시간이 오래 걸리는 것 같습니다.")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.")
        return False
    except Exception as e:
        print(f"❌ 오류 발생: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_test_image():
    """테스트 이미지 파일 존재 여부 확인"""
    print("=" * 60)
    print("0. 테스트 이미지 확인")
    print("=" * 60)
    
    project_root = Path(__file__).parent.parent
    image_path = project_root / TEST_IMAGE_PATH
    
    print(f"이미지 경로: {image_path}")
    
    if image_path.exists():
        file_size = image_path.stat().st_size
        print(f"✅ 이미지 파일 존재")
        print(f"   파일 크기: {file_size:,} bytes ({file_size / 1024:.2f} KB)")
        print()
        return True
    else:
        print(f"❌ 이미지 파일이 존재하지 않습니다!")
        print(f"   경로를 확인하세요: {image_path}")
        print()
        return False

def main():
    """메인 테스트 함수"""
    print("\n")
    print("=" * 60)
    print("Flask API 테스트 시작")
    print("=" * 60)
    print()
    
    # 테스트 이미지 확인
    if not check_test_image():
        print("테스트를 중단합니다.")
        return
    
    # 헬스 체크
    if not test_health_check():
        print("서버가 실행되지 않았습니다. 서버를 먼저 시작하세요:")
        print("  python app.py")
        print("  또는")
        print("  python start.py")
        return
    
    # 이상 탐지 테스트
    test_anomaly_detection()
    
    print("\n" + "=" * 60)
    print("테스트 완료")
    print("=" * 60)
    print()

if __name__ == "__main__":
    main()

