export interface RadiologyReportRequest {
  radiologyRequestId: number;
  patientId: number;
  employeeId: number;
  deptId: number;
  symptomDetail?: string | null;
  memo?: string | null;
  entryDate: string; // yyyy-MM-dd 형식
  detailImageAddress: string;
  view?: XrayView;
}

export type XrayView = "AP" | "PA";

export interface RadiologyReportResponse {
  heatmapUrl: string | null;
  predictedDiseases: PredictedDisease[];
  warning: string | null;
  engineStatus?: string;
  // xray-rag 자신이 계산한 확신도와 사유(services/xray-rag 의 Uncertainty).
  // engineStatus 와 다른 축이다 — engineStatus 는 "실제 모델이 돌았나",
  // 이건 "돈 결과를 얼마나 믿을 수 있나"다. 둘 다 Java DTO 가 선언하지 않아
  // 화면에 도달하지 못하고 있었다(F-H4).
  uncertainty?: XrayUncertainty | null;
  // 어느 ROI 분할기가 실제로 구성됐는지: "pspnet" | "cv" | "mock".
  // engineStatus 와 또 다른 축이다 — 검색의 기본 경로는 ROI 마스크를 쓰지
  // 않으므로 ROI 가 mock 으로 떨어져도 엔진은 real 일 수 있다. 그 조합을
  // 한 값으로 합치면 어느 쪽이 내려간 것인지 화면에서 말할 수 없다.
  roiStatus?: string;
}

export interface XrayUncertainty {
  level?: string | null;
  reasons?: string[] | null;
}

export interface PredictedDisease {
  disease: string;
  score: number;
  reason: string;
}

/**
 * 이미지 파일과 메타데이터를 함께 전송하여 AI 분석을 수행합니다.
 * @param file 이미지 파일
 * @param patientId 환자 ID
 * @param employeeId 근무자 ID
 * @param deptId 부서 ID
 * @param entryDate 등록일자 (yyyy-MM-dd)
 * @param symptomDetail 증상 상세 (선택)
 * @param memo 메모 (선택)
 * @returns AI 분석 결과
 */
// X-ray 추론은 CPU 에서 10~15초가 걸린다. 컨테이너 안에서 잰 내역:
//   SQUID 이상탐지(reconstruct)  ~4초
//   DenseNet 임베딩(embed_all)   ~8초   전역 + 좌폐 + 우폐 + 심장 4회
//   나머지(전처리·마스크·검색)     ~0.3초
//
// 이 함수는 http/client 의 기본값 15000ms 를 그대로 쓰고 있었다. 추론 시간이
// 그 값 바로 아래라, 같은 영상이라도 어떤 요청은 통과하고 어떤 요청은
// 타임아웃났다 — 브라우저가 먼저 포기했을 뿐 서버는 정상 처리 중이었는데
// 사용자에게는 분석 실패로 보였다.
//
// 값은 Java 의 http.client.rest-template.read-timeout-ms(180000ms) 보다 작게
// 둔다. 이쪽이 더 크면 Java 가 이미 포기한 요청을 브라우저가 계속 기다리게
// 된다. GPU(T4 급)를 붙이면 추론이 2~4초로 떨어지므로 그때 다시 줄인다.
export const RADIOLOGY_ANALYZE_TIMEOUT_MS = 60000;

export async function uploadAndAnalyzeImage(
  file: File,
  patientId: number,
  employeeId: number,
  deptId: number,
  entryDate: string,
  view: XrayView = "PA",
  symptomDetail?: string | null,
  memo?: string | null
): Promise<RadiologyReportResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("patientId", String(patientId));
  formData.append("employeeId", String(employeeId));
  formData.append("deptId", String(deptId));
  formData.append("entryDate", entryDate);
  formData.append("view", view);
  if (symptomDetail) {
    formData.append("symptomDetail", symptomDetail);
  }
  if (memo) {
    formData.append("memo", memo);
  }

  // multipart/form-data 요청을 위해 axios를 직접 사용
  const { http } = await import("./http/client");
  const instance = http();
  const response = await instance.post<RadiologyReportResponse>(
    "/api/radiology/upload-and-analyze",
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
      timeout: RADIOLOGY_ANALYZE_TIMEOUT_MS,
    }
  );

  return response.data;
}

