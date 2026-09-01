"use client";

import { useState, useRef } from "react";
import { Badge, Button, EmptyState, Panel } from "@/components/ui";
import styles from "./AIReport.module.css";
import {
  PredictedDisease,
  uploadAndAnalyzeImage,
  XrayUncertainty,
  XrayView,
} from "@/services/radiology";
import { AI_DISABLED_NOTICE, isAiEnabled } from "@/services/aiFeatures";

const EXCLUDED_DISEASE_TAGS = new Set(["no_finding", "support_devices"]);
const MAX_VISIBLE_DISEASES = 3;

interface AIReportProps {
  patientId?: number;
  employeeId?: number;
  deptId?: number;
  entryDate?: string; // yyyy-MM-dd 형식
}

function getVisiblePredictedDiseases(diseases: PredictedDisease[] | undefined): PredictedDisease[] {
  return (diseases || [])
    .filter((item) => item.disease && !EXCLUDED_DISEASE_TAGS.has(item.disease.toLowerCase()))
    .sort((a, b) => b.score - a.score)
    .slice(0, MAX_VISIBLE_DISEASES);
}

export default function AIReport({
  patientId,
  employeeId,
  deptId,
  entryDate,
}: AIReportProps) {
  const [uploadedImage, setUploadedImage] = useState<string | null>(null);
  const [resultImage, setResultImage] = useState<string | null>(null);
  const [predictedDiseases, setPredictedDiseases] = useState<PredictedDisease[]>([]);
  const [warning, setWarning] = useState<string | null>(null);
  const [engineStatus, setEngineStatus] = useState<string | null>(null);
  const [roiStatus, setRoiStatus] = useState<string | null>(null);
  const [uncertainty, setUncertainty] = useState<XrayUncertainty | null>(null);
  const [view, setView] = useState<XrayView>("PA");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const selectedFileRef = useRef<File | null>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      // 이미지 파일인지 확인
      if (!file.type.startsWith("image/")) {
        alert("이미지 파일만 업로드 가능합니다.");
        return;
      }

      // 파일 객체 저장
      selectedFileRef.current = file;

      // FileReader를 사용하여 이미지 미리보기 생성
      const reader = new FileReader();
      reader.onloadend = () => {
        setUploadedImage(reader.result as string);
      };
      reader.readAsDataURL(file);

      // 에러 초기화
      setError(null);
    }
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleRemoveImage = () => {
    setUploadedImage(null);
    setResultImage(null);
    setPredictedDiseases([]);
    setWarning(null);
    setEngineStatus(null);
    setUncertainty(null);
    setError(null);
    selectedFileRef.current = null;
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleAnalyze = async () => {
    if (!uploadedImage || !selectedFileRef.current) {
      alert("이미지를 먼저 업로드해주세요.");
      return;
    }

    // 필수 파라미터 확인
    if (!patientId || !employeeId || !deptId || !entryDate) {
      alert("환자 정보가 없습니다. 진료실에서 환자를 선택해주세요.");
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const file = selectedFileRef.current;
      const response = await uploadAndAnalyzeImage(
        file,
        patientId,
        employeeId,
        deptId,
        entryDate,
        view
      );

      setResultImage(response.heatmapUrl || uploadedImage);
      setPredictedDiseases(getVisiblePredictedDiseases(response.predictedDiseases));
      setWarning(response.warning || null);
      setEngineStatus(response.engineStatus || null);
      setRoiStatus(response.roiStatus || null);
      setUncertainty(response.uncertainty || null);
    } catch (err: unknown) {
      console.error("AI 분석 오류:", err);
      const apiError = err as { response?: { data?: { error?: string } }; message?: string };
      const errorMessage =
        apiError.response?.data?.error ||
        apiError.message ||
        "AI 분석 중 오류가 발생했습니다.";
      setError(errorMessage);
      alert(`AI 분석 실패: ${errorMessage}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Panel className={styles.container} title="AI 리포트">
      {/* 업로드된 이미지 표시 영역 */}
      <div className={styles.imageSection}>
        {uploadedImage ? (
          <div className={styles.imageContainer}>
            <img
              src={uploadedImage}
              alt="업로드된 이미지"
              className={styles.uploadedImage}
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className={styles.removeButton}
              onClick={handleRemoveImage}
              aria-label="이미지 제거"
            >
              ×
            </Button>
          </div>
        ) : (
          <EmptyState title="이미지를 업로드하거나 선택하세요" />
        )}
      </div>

      <div className={styles.controlSection}>
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileSelect}
          accept="image/*"
          style={{ display: "none" }}
        />
        <Button type="button" variant="secondary" onClick={handleUploadClick}>
          이미지 업로드
        </Button>
        <select
          className={styles.viewSelect}
          value={view}
          onChange={(event) => setView(event.target.value as XrayView)}
          aria-label="X-ray 촬영 방향"
        >
          <option value="PA">PA</option>
          <option value="AP">AP</option>
        </select>
        {isAiEnabled() ? (
        <Button
          type="button"
          variant="secondary"
          disabled={!uploadedImage || isLoading}
          loading={isLoading}
          onClick={handleAnalyze}
        >
          {isLoading ? "분석 중..." : "AI 분석"}
        </Button>
        ) : (
          // DR 구성에는 xraygraph 가 없다. 버튼을 두면 눌러서 503 을 받는데,
          // 화면에서는 "없는 기능" 과 "고장" 이 구별되지 않는다.
          <span role="note">{AI_DISABLED_NOTICE}</span>
        )}
      </div>

      {/* 결과 이미지 표시 영역 */}
      {resultImage && (
        <div className={styles.resultImageSection}>
          <div className={styles.imageContainer}>
            <img
              src={resultImage}
              alt="분석 결과 이미지"
              className={styles.uploadedImage}
            />
          </div>
        </div>
      )}

      {/* 분석 결과 텍스트 영역 */}
      {(predictedDiseases.length > 0 || warning) && (
        <div className={styles.resultTextSection}>
          <div className={styles.resultContent}>
            {/*
              GC-3 fail-closed: "real" 정확 일치만 무표시다. 값이 없거나 계약 밖이면
              "괜찮다"가 아니라 "모른다"로 드러낸다 — 예전에는 engineStatus 가
              없을 때 이 경고 자체가 안 떠서, 값을 떨어뜨리는 경계 결함이 화면에서
              정상 상태와 구별되지 않았다(F-H4 가 눈에 띄지 않은 이유).
            */}
            {engineStatus !== "real" && (
              <div role="status" className={styles.engineWarning}>
                <Badge tone="warning">{engineStatus || "미확인"}</Badge>
                <span>
                  {engineStatus ? (
                    <>
                      이 결과는 <strong>{engineStatus}</strong> 엔진에서 생성되었습니다. 실제 모델
                      추론이 아니므로 임상 판단에 사용할 수 없습니다.
                    </>
                  ) : (
                    <>
                      이 결과를 만든 엔진이 <strong>미확인</strong>입니다. 실제 모델 추론인지
                      확인되지 않았으므로 임상 판단에 사용할 수 없습니다.
                    </>
                  )}
                </span>
              </div>
            )}
            {/*
              ROI 분할 출처. engineStatus 와 또 다른 축이다.

              경고는 두 경우만이다. "mock" 은 입력과 무관한 고정 타원이라 ROI별
              통계와 임베딩이 영상에 대해 아무 말도 하지 않는다. 값이 없으면
              어느 쪽인지 모르므로 fail-closed 로 같이 경고한다(GC-3).

              "cv" 와 "pspnet" 은 경고하지 않고 이름만 남긴다. 둘 다 영상에 실제로
              반응하는 분할이고, 현재 기본값이 cv 라 여기서 경고를 띄우면 모든
              추론마다 발화해 아무도 읽지 않는 경고가 된다 — 그러면 정작 mock 으로
              떨어진 순간을 구별할 수 없게 된다.
            */}
            {roiStatus !== "cv" && roiStatus !== "pspnet" ? (
              <div role="status" className={styles.engineWarning}>
                <Badge tone="warning">{roiStatus || "미확인"}</Badge>
                <span>
                  {roiStatus ? (
                    <>
                      병변 위치 분할이 <strong>{roiStatus}</strong> 입니다. 입력 영상에 반응하지
                      않는 고정 영역이므로, 부위별 소견은 이 영상의 해부 구조와 무관합니다.
                    </>
                  ) : (
                    <>
                      병변 위치 분할기가 <strong>미확인</strong>입니다. 부위별 소견이 이 영상의
                      해부 구조에서 나온 것인지 확인되지 않았습니다.
                    </>
                  )}
                </span>
              </div>
            ) : (
              <div className={styles.engineWarning}>
                <Badge tone="neutral">{roiStatus}</Badge>
                <span>부위별 소견은 {roiStatus} 분할이 잡은 영역을 기준으로 계산되었습니다.</span>
              </div>
            )}
            {/*
              xray-rag 자신이 계산한 확신도. engineStatus 와 다른 축이라 따로 낸다 —
              "실제 모델이 돌았다"와 "그 결과를 믿을 수 있다"는 다른 정보다.
              level 만 쓰고 reasons 를 버리면 "확신 없음"의 근거가 화면에서 사라진다.
              uncertainty 자체가 없을 때는 경고하지 않는다 — 없는 것은 "확신 없음"의
              근거가 아니다(GC-2). 그 경우는 위 엔진 축이 미확인으로 알린다.
            */}
            {uncertainty?.level === "high" && (
              <div role="alert" className={styles.engineWarning}>
                <Badge tone="warning">확신 낮음</Badge>
                <span>
                  이 추론은 유사 사례 근거가 약합니다.
                  {uncertainty.reasons && uncertainty.reasons.length > 0 ? (
                    <ul className={styles.uncertaintyReasons}>
                      {uncertainty.reasons.map((reason, index) => (
                        <li key={`${index}-${reason}`}>{reason}</li>
                      ))}
                    </ul>
                  ) : null}
                </span>
              </div>
            )}
            <span className={styles.resultLabel}>추론된 상병:</span>
            {predictedDiseases.length > 0 ? (
              <ul className={styles.predictionList}>
                {predictedDiseases.map((item, index) => (
                  <li key={`${item.disease}-${index}`} className={styles.predictionItem}>
                    <div className={styles.predictionHeader}>
                      <span className={styles.resultValue}>{item.disease}</span>
                      <span className={styles.score}>{item.score.toFixed(3)}</span>
                    </div>
                    <p className={styles.reason}>{item.reason}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <span className={styles.normal}>추론된 상병 없음</span>
            )}
            {warning && <p className={styles.warning}>{warning}</p>}
          </div>
        </div>
      )}

      {/* 에러 메시지 표시 */}
      {error && (
        <div className={styles.errorMessage}>
          <p>{error}</p>
        </div>
      )}
    </Panel>
  );
}
