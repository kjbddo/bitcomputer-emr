# AWS 배포 설계

현재 구조는 [09-current-infrastructure.md](09-current-infrastructure.md) 에 있다.
이 문서는 **거기서 AWS 로 어떻게 옮길지** 를 정한다.

아직 배포하지 않았다. 결정된 것과 열려 있는 것을 구분해 적는다.

---

## 1. 전체 구조

```
브라우저
  │
  ▼
CloudFront ──────── WAF(us-east-1 스코프), TLS, /_next/static/* 캐시
  │  VPC origin
  ▼
ALB (private subnet) ─── Gateway API 가 생성·소유
  │
  ├── /*      frontend 파드      Next 서버(SSR)
  └── /api/*  spring-boot 파드
                │
                ├── prescription-api / certificate-api / xraygraph / llm-gateway   ClusterIP, 외부 노출 없음
                │      └── validation-agent  ← AmazonMQ
                │
                └── RDS(MySQL) / ElastiCache(Redis) / AmazonMQ / ArangoDB(인클러스터)

노드는 전부 private subnet. EKS 엔드포인트도 private.
```

**단일 오리진이다.** 프론트와 API 가 같은 CloudFront 도메인 아래 있으므로 CORS 와
`SameSite` 재설계가 필요 없다. 지금 인증이 쿠키 기반(`withCredentials`,
`XSRF-TOKEN`)이라 이 선택이 중요하다.

### 1.1 프론트를 정적으로 빼지 않는 이유

`apps/web` 에 **`src/middleware.ts` 와 API 라우트 둘**(`/api/diseases`,
`/api/diagnoses`)이 있다. Next 정적 export(`output: 'export'`)는 둘 다 지원하지
않는다.

걷어내면 정적 배포가 가능하지만 코드를 고쳐야 하고, 그 수정은 배포와 별개의
회귀 위험이다. **컨테이너로 올리면 코드 수정이 0 이다.**

nginx 를 앞에 따로 두지 않는다. TLS·라우팅·캐시·압축을 CloudFront 와 ALB 가 이미
하고, Next 서버는 어차피 떠 있어야 하므로 홉만 늘어난다.

### 1.2 ALB 를 사설로 두는 이유

CloudFront VPC origin 을 쓰면 ALB 가 private subnet 에 있어도 CloudFront 가 닿는다.

| | 인터넷 페이싱 + 프리픽스 리스트 | VPC origin |
|---|---|---|
| ALB 위치 | public subnet | **private subnet** |
| WAF 우회 | SG 설정 실수 시 가능 | **경로 자체가 없음** |
| 테라폼 적용 단계 | 2단계 | 2단계 (차이 없음) |

**적용 단계는 어느 쪽이든 2단계다.** CloudFront 오리진에 ALB DNS 이름이 필요한데
그 이름은 Gateway 가 ALB 를 만들어야 정해지고(임의 접미사), Route53 이 범위 밖이라
별칭으로 우회할 수도 없다. 그러면 VPC origin 쪽이 추가 비용 없이 더 안전하다.

> 리전 지원 여부를 먼저 확인한다. 안 되면 인터넷 페이싱 + CloudFront 관리형
> 프리픽스 리스트(`com.amazonaws.global.cloudfront.origin-facing`)로 내려온다.
> 그때도 나머지 구조는 그대로다.

---

## 2. 도구 경계

```
테라폼    VPC, 서브넷(EKS 태그 포함), RT, IGW, NAT, VPC 엔드포인트
          SG, S3 ×2, RDS, ElastiCache, AmazonMQ, bastion
          CloudFront + WAF + VPC origin        ← ALB 생성 후 2차 적용

eksctl    클러스터, 노드그룹, OIDC, IRSA, 애드온

매니페스트  Gateway API CRD, AWS LB 컨트롤러, Gateway/HTTPRoute
          앱 배포 전부 (ArgoCD)
```

### 2.1 테라폼에서 뺀 것

| 자원 | 이유 |
|---|---|
| EKS | eksctl 이 IRSA·애드온을 훨씬 적은 코드로 처리한다 |
| ALB / 리스너 / 리스너룰 / TG | Gateway API 컨트롤러가 만들고 소유한다 |
| ASG | EKS 관리형 노드그룹이 ASG 를 직접 만든다 |
| ~~RDS~~ | **철회.** 테라폼이 만든다 — `deletion_protection` + `prevent_destroy` 로 잠근다 |
| Route53 / VPN | 나중 단계 |
| 정적 콘텐츠 S3 | 프론트가 컨테이너로 가면서 할 일이 없어졌다 |

`eksctl` 을 쓰는 것이 IaC 가 아닌 것은 아니다. `cluster.yaml` 도 선언적이고 뒤에서
CloudFormation 이 상태를 관리한다.

### 2.2 eksctl 로 갈 때 주의사항

**서브넷 태그는 테라폼이 붙인다.** eksctl 에 기존 서브넷을 넘기면 **eksctl 은 그
서브넷에 태그를 추가하지 않는다.** 서브넷 소유자가 테라폼이므로 태그도 테라폼
몫이다.

```hcl
# public
"kubernetes.io/role/elb"          = "1"
# private
"kubernetes.io/role/internal-elb" = "1"
```

없으면 LB 컨트롤러가 서브넷을 못 찾고, **클러스터를 다 만든 뒤 Gateway 가 안 뜨는
형태로** 드러난다.

**프라이빗 클러스터면 VPC 엔드포인트도 테라폼이 만든다.** eksctl 의
`privateCluster.enabled` 는 자기가 VPC 를 만들 때만 엔드포인트를 함께 만든다.

```yaml
privateCluster:
  enabled: true
  skipEndpointCreation: true    # 테라폼이 이미 만들었다
```

필요한 엔드포인트:

```
ec2  ecr.api  ecr.dkr  s3(gateway)  logs  sts  elasticloadbalancing  autoscaling
```

빠뜨리면 노드는 조인되는데 **이미지 풀이나 로그 전송에서 걸린다.**

**SG 순환 참조를 피한다.** 클러스터 SG 는 eksctl 이 만들고 RDS·ElastiCache·
AmazonMQ SG 는 테라폼이 만든다. 테라폼이 클러스터 SG ID 를 참조하면 순환이
생기므로, **소스를 CIDR(private subnet 대역)로 준다.**

**삭제는 정확히 역순이다.**

```
1. 매니페스트 삭제 (Gateway → ALB 회수)
2. eksctl delete cluster
3. terraform destroy
```

ALB 가 살아 있는 채로 서브넷을 지우려 하면 테라폼이 오래 매달린 뒤 실패한다.

### 2.3 Gateway API 주의사항

- **AWS LB 컨트롤러 v2.13 이상**이라야 Gateway API 를 받는다
- **Gateway API CRD 를 따로 설치**한다. 쿠버네티스에 내장돼 있지 않다
- 인증서·스킴 같은 **ALB 고유 설정은 `LoadBalancerConfiguration` CRD** 로 붙인다.
  Gateway API 표준 리소스만 보고 있으면 "왜 HTTPS 가 안 되지"에서 막힌다
- **네임스페이스를 넘는 라우팅은 `ReferenceGrant`** 가 필요하다
- 서브넷 태그는 Ingress 를 쓰든 Gateway 를 쓰든 **똑같이 필요하다**

---

## 3. 적용 순서

```
1. 테라폼 1차   VPC, 서브넷, 엔드포인트, SG, S3, RDS, ElastiCache, AmazonMQ, bastion
2. eksctl       클러스터, 노드그룹, OIDC, IRSA, 애드온
3. 매니페스트    Gateway API CRD → LB 컨트롤러 → Gateway   (ALB 생성됨)
4. 테라폼 2차   CloudFront + WAF + VPC origin (ALB 를 data 로 참조)
```

**4가 3에 의존한다.** 한 번에 `terraform apply` 를 돌리면 실패한다. 이 순서를
문서와 CI 양쪽에 못박는다.

---

## 4. 상태 관리

### 4.1 레이어

```
00-bootstrap   state 버킷, GH Actions OIDC 역할     ← 로컬 state 로 만들고 마이그레이션
10-network     VPC, subnet, RT, IGW, NAT, 엔드포인트
20-security    SG, WAF, IAM
30-data        RDS, ElastiCache, AmazonMQ, S3 ×2, EFS
40-edge        CloudFront + VPC origin              ← 3단계 이후에만 적용 가능

키: s3://<bucket>/<env>/<layer>/terraform.tfstate
```

잠금은 DynamoDB 대신 **S3 네이티브 락**(`use_lockfile = true`)을 쓴다. 테이블
하나가 줄어든다.

### 4.2 레이어 간 참조는 SSM Parameter Store

`terraform_remote_state` 는 하위 레이어의 state 구조에 상위를 결합시킨다.
리팩터링하면 같이 깨진다. 출력을 SSM 에 쓰면 결합이 **이름 하나**로 줄고,
**K8s 매니페스트와 CI 도 같은 값을 읽을 수 있다.**

### 4.3 환경 분리는 workspace 가 아니라 키 접두사

workspace 는 지금 어느 환경인지가 명령에 드러나지 않아, 프로드에 dev 를 미는
사고가 나기 쉽다.

---

## 5. 데이터 계층

| 지금 | AWS | 비고 |
|---|---|---|
| `mysql` 컨테이너 | **RDS MySQL 8.0** | 인스턴스·부속 전부 테라폼 |
| `redis` 컨테이너 | **ElastiCache** | |
| `rabbitmq` 컨테이너 | **AmazonMQ** | 엔진 버전 확인 필요 |
| `arangodb` 컨테이너 | **인클러스터 + EBS** | 관리형 등가물 없음 |

### 5.1 ArangoDB 가 유일한 인클러스터 상태 저장소다

EBS 는 AZ 에 묶이므로 노드 장애 시 **같은 AZ 로 재스케줄**되어야 한다.
`topology.kubernetes.io/zone` 노드 어피니티와 EBS CSI 의 `WaitForFirstConsumer`
바인딩 모드를 함께 쓴다.

### 5.2 EBS 를 미리 만들지 않는다

정적 PV 로 미리 만든 볼륨을 물리면 파드가 그 AZ·그 노드에 못 박히고, 테라폼이
볼륨 생명주기를 K8s 가 바인딩을 각각 쥐어 서로 싸운다.

**테라폼은 EBS CSI IRSA 역할만 만들고**(실제로는 eksctl 이 처리), 볼륨은 PVC 가
동적으로 만들게 둔다. StorageClass 는 매니페스트로 관리한다.

---

## 6. 볼륨과 파일 저장소

### 6.1 `images-storage` — 1단계는 EFS

**세 곳이 쓴다.**

```
쓰기   Spring ImageStorageUtil.saveImage()      업로드 원본
읽기   flask-radiology                          Spring 이 경로 문자열만 넘기고 flask 가 직접 읽는다
서빙   Spring WebMvcConfig  /images/**          브라우저에 원본·오버레이 정적 서빙
```

`xraygraph` 는 이 볼륨을 **쓰지 않는다.** Spring 이 파일을 읽어 multipart
바이트로 POST 한다. 그래서 RWX 공유가 필요한 것은 **flask 경로 하나뿐**이고,
`RADIOLOGY_ENGINE=xray` 가 기본이라 지금 그 경로는 쓰이지 않는다.

그럼에도 **EBS 로는 안 된다** — 셋 중 둘(Spring 쓰기·서빙)이 같은 파드라도,
flask 를 띄우는 순간 ReadWriteMany 가 필요해진다.

| | S3 | EFS |
|---|---|---|
| 코드 수정 | **세 곳 전부** | 없음 |
| 정적 서빙 | 프리사인 URL 또는 CloudFront 오리진 추가 | 그대로 |
| RWX | 해당 없음(객체 저장소) | 지원 |
| 단가 | GB-월 기준 가장 쌈 | S3 의 7~10배 |

**1단계는 EFS 로 간다.** 근거 셋이다.

**첫째, S3 로 가려면 세 곳을 동시에 고쳐야 하고 그중 하나가 브라우저가 직접 보는
정적 서빙이다.** 배포와 코드 변경을 한 번에 묶으면 문제가 났을 때 원인이 둘로
갈린다 — 인프라가 잘못된 것인지 코드가 잘못된 것인지 구분하는 데 시간이 든다.

**둘째, 이 볼륨은 크지 않다.** X-ray 원본 한 장이 46KB 다. 파생 산출물까지 포함한
로컬 `storage/` 전체가 471파일에 109MB 다. **EFS 단가가 S3 의 10배여도 GB 단위
용량에서는 절대 금액 차이가 무의미하다.** 단가 비교가 의미를 갖는 것은 TB 규모
부터다.

**셋째, 지금 RWX 가 필요한 경로는 실제로 쓰이지 않는다.** `RADIOLOGY_ENGINE=xray`
가 기본이라 flask 는 호출되지 않는다. 그런데도 EBS 를 못 쓰는 이유는 **flask 를
켜는 순간 조용히 깨지기 때문**이다. EFS 는 그 경로를 켜든 끄든 동작한다.

> **뒤집을 조건을 미리 적어 둔다.** 업로드가 수십 GB 를 넘거나 정적 서빙을
> CloudFront 로 옮기게 되면 S3 로 간다. 그전에는 EFS 가 싸다 — 금액이 아니라
> **바꾸지 않아도 되는 코드**가 싸다.

**2단계에서 S3 로 옮기는 순서:**

```
1. ImageStorageUtil 을 인터페이스로 분리 (로컬 구현 / S3 구현)
2. 정적 서빙을 CloudFront → S3 로 이관 (Spring 에서 떼어낸다)
3. flask 경로는 마지막 — 어차피 지금 안 쓰인다
```

### 6.2 경로 탐색을 먼저 고쳐야 한다

`ImageStorageUtil.getProjectRoot()` 와 `WebMvcConfig` 가 **작업 디렉터리에서
`BitComputer` 폴더를 위로 훑어 올라가며 찾는다.** 못 찾으면 현재 디렉터리에
만든다. `WebMvcConfig` 는 후보 경로 셋을 순서대로 등록한다.

`image.storage.path` 프로퍼티가 이미 있는데 `getProjectRoot()` 가 그것을 무시하고
자체 탐색을 한다.

**K8s 에서 이 탐색이 다른 곳을 가리키면 예외가 아니라 빈 디렉터리를 만들고
정상처럼 뜬다.** 이전 볼륨의 파일이 안 보이는 형태로만 드러난다. **이전 전에
프로퍼티를 따르도록 정리한다.**

### 6.3 SQUID 가중치 — 바인드 마운트를 대체해야 한다

```yaml
xraygraph:
  volumes:
    - ../services/radiology-legacy:/app/weights:ro
  environment:
    SQUID_MODEL_DIR: /app/weights/squid_exp1_256_mask
```

없으면 `engineStatus` 가 `real` → `mock` 으로 떨어진다. K8s 에는 이런 마운트가
없다.

**S3 + initContainer 로 간다**(11 §4.4). 이미지에 굽지 않는 이유는 가중치가 코드와
다른 주기로 바뀌고, 구우면 `xraygraph`·`flask-radiology` 두 이미지에 같은 파일이
중복되기 때문이다.

`flask-radiology` 를 안 띄우더라도 **이 디렉터리는 지울 수 없다.**

### 6.4 갱신이 필요한 저장소

| 대상 | 출처 | 갱신 방식 |
|---|---|---|
| RDS `disease` / `diagnose` | 엑셀 2개 (50,941 / 505,954행) | K8s Job |
| ArangoDB `bitcomputer_graph` | 엑셀 + 합성 케이스 | K8s Job |
| ArangoDB `xray_graph_db` | CheXpert 시드 202건 | 배치 Job |

**엑셀 → ArangoDB CI 에서 주의할 것 둘:**

`import_to_arango.py` 는 **기본이 truncate 다.** 합성 케이스를 살리려면 원본 적재
후 `--append` 로 합성을 다시 넣어야 한다. 순서가 뒤바뀌면 합성 120건이 사라진다.

**Job 이 끝난 뒤 건수를 검증해야 한다.** 적재는 "성공"이라 말하면서 내용이 틀릴 수
있다. `visits`·`diagnoses`·`order_lines` 를 세고 기대값과 다르면 실패시킨다.

---

## 7. 설정과 시크릿

| 성격 | 예 | 보관 |
|---|---|---|
| 자격증명 | `LLM_API_KEY`, DB 비밀번호, `JWT_SECRET` | Secrets Manager |
| 접속 정보 | `*_BASE_URL`, 엔드포인트 | Parameter Store (테라폼 출력) |
| 동작 토글 | `USE_PSPNET_ROI`, `USE_TORCH_*`, `LLM_PROVIDER` | ConfigMap |
| 빌드 시점 | `NEXT_PUBLIC_API_BASE_URL` | 이미지에 굽힘 |

### 7.1 토글 기본값이 두 곳에 있으면 조용히 어긋난다

`USE_PSPNET_ROI` 가 `app/config.py` 와 `docker-compose.yml` 양쪽에 기본값을 갖는데
**적재 스크립트는 호스트에서 돌아 compose 를 거치지 않았다.** 그 결과 저장 코퍼스는
`pspnet`, 질의는 `cv` 인 상태가 만들어졌고 **양쪽 다 정상으로 보였다** — 컨테이너
healthy, 시더 "202건 적재 성공", 검색도 결과를 냄.

지금은 `test_toggle_defaults_match_compose.py` 가 막는다.

**K8s 에서 ConfigMap 과 코드 기본값 사이에 같은 함정이 재발한다.** 적재 Job 과
런타임 파드가 **같은 ConfigMap 을 참조**하도록 배선한다.

### 7.2 `NEXT_PUBLIC_API_BASE_URL`

단일 오리진이므로 빈 값 + 상대 경로로 두면 **도메인이 바뀌어도 재빌드가 필요
없다.** 나중에 Route53 을 붙일 때 이득이다.

`apps/web/src/services/http/client.ts` 가 빈 값이면 `http://localhost:8080` 으로
폴백하므로 **한 줄 수정이 필요하다.**

---

## 8. 노드 사이징

실측(CPU 14코어) 기준이다.

| 파드 | 자원 | 비고 |
|---|---|---|
| `xraygraph` | **CPU 전부 + 1.4GB** | 추론 3~4초가 이 전제 |
| `frontend` | Next SSR, 메모리 여유 | |
| `spring-boot` | 650MB | |
| `arangodb` | 330MB + EBS | |
| 나머지 4개 | 각 60~120MB | |

**`xraygraph` 가 사이징 하한을 정한다.** CPU 가 적은 노드에 올리면 추론이 다시
느려지고 웹 타임아웃 60초에 근접한다.

**노드 그룹을 둘로 나누는 것을 고려한다** — 일반 워크로드용과 AI 워크로드용.
taint/toleration 으로 가른다. `xraygraph` 가 CPU 를 다 쓰는 동안 프론트가 같은
노드에 있으면 화면 응답이 같이 느려진다.

---

## 9. CI / CD

```
코드 저장소   GitHub
CI           GitHub Actions (지금 9잡)
CD           ArgoCD
```

**GitOps 매니페스트는 별도 레포를 권한다.** 같은 레포에 두면 CD 가 이미지 태그를
커밋 → 그 커밋이 앱 CI 를 다시 트리거하는 고리가 생긴다. 경로 필터로 막을 수는
있지만 조용히 깨지는 종류다.

```
bitcomputer-emr      apps/ services/ packages/ deploy/terraform/
bitcomputer-gitops   환경별 overlay, ArgoCD Application
```

---

## 10. GCP DR

AI 관련 API 를 **전부 배제**하고 EMR 코어만 가져간다.

```
가져감    frontend, spring-boot, Cloud SQL
두고 감    prescription-api, certificate-api, validation-agent, llm-gateway,
          xraygraph, flask-radiology, ArangoDB, AmazonMQ
```

ArangoDB(처방 그래프 전용)와 RabbitMQ/AmazonMQ(검증 job 전용)는 AI 를 걷어내면
소비자가 없어 함께 빠진다. **결과적으로 DR 상태 저장소는 Cloud SQL 하나**다.

### 10.1 별도 이미지를 만들지 않는다

`LLM_PROVIDER=stub` 이라는 seam 이 이미 있고 CI 의 `compose e2e` 가 매번 그 형상으로
돈다. 이미지를 갈래로 나누면 빌드·테스트 표면이 두 배가 되고 **두 갈래가 조용히
어긋난다.** 같은 이미지, 다른 배포 프로파일로 간다.

### 10.2 먼저 재야 할 것

**Spring 이 AI 서비스 없이 정상 동작하는지 확인된 바 없다.** 화면이 깨지는지, 빈
상태로 뜨는지, 예외를 던지는지 모른다.

이건 DR 뿐 아니라 **AWS 배포 순서**에도 걸린다 — 코어부터 올리고 AI 를 나중에
붙일 수 있는지가 그 답에 달려 있다.

### 10.3 동기화

**1단계 — VPN 없이**

```
RDS --mysqldump--> S3 --Storage Transfer--> GCS --import--> Cloud SQL
```

RPO 가 시간 단위여도 되면 충분하고 사설망 연결이 필요 없다.

**2단계 — RPO 를 분 단위로 줄여야 할 때**

GCP Database Migration Service 로 RDS 를 외부 소스로 두고 연속 CDC 를 건다.
`AWS Site-to-Site VPN ↔ GCP HA VPN`(BGP), RDS `binlog_format=ROW`, binlog 보존
설정이 필요하다.

**마스터 코드는 동기화 대상이 아니다.** `disease`·`diagnose` 는 엑셀에서
재생성되는 파생 데이터다. GCP 쪽에서 같은 스크립트를 돌리면 된다. 동기화가
필요한 것은 **환자·진료 이력** 뿐이다 — 56만 행이 대상에서 빠진다.

---

## 11. 결정된 것 / 열린 것

### 결정

```
진입점            CloudFront (WAF 는 여기에만)
프론트            컨테이너로 클러스터, 정적 export 안 함
ALB              private subnet + CloudFront VPC origin (리전 지원 확인 후)
라우팅            Gateway API (Ingress 아님)
EKS              eksctl, 테라폼 밖
MySQL            RDS
RabbitMQ         AmazonMQ
Redis            ElastiCache
ArangoDB         인클러스터 + EBS 동적 프로비저닝
images-storage   1단계 EFS (코드 수정 0, 용량 100MB 대라 단가 차이 무의미), 2단계 S3
테라폼 제외       EKS, ALB/리스너/TG/ASG, Route53, VPN, 정적 콘텐츠 S3
GCP DR           AI 전면 배제, Cloud SQL 하나
```

### 열림

```
1. 이미지 저장소 GHCR vs ECR        프라이빗 클러스터면 ECR 이 유리(NAT 회피, IRSA 인증)
2. ArgoCD 태그 갱신                 CI 커밋 vs Image Updater
3. ~~프론트 헬스 엔드포인트~~        완료 — `/api/health` 추가, compose 헬스체크도 함께
4. 노드 그룹 분리 여부               AI 워크로드 격리
5. AmazonMQ 엔진 버전 / 단일 vs 클러스터
6. 로그 수집 경로                   Fluent Bit → S3 직접 vs CloudWatch 경유
7. CloudFront VPC origin 리전 지원 확인 (`ap-northeast-2`)
```

### 코드 수정이 필요한 것

```
1. ImageStorageUtil / WebMvcConfig 경로 탐색 → 프로퍼티 준수      (이전 전 필수)
2. http/client.ts 빈 baseURL → 상대 경로                        (한 줄)
3. SQUID 가중치를 S3 에 올리고 initContainer 로 받게 한다 (11 §4.4)
```

완료:

```
프론트 /api/health   force-dynamic, 상류를 확인하지 않음. compose 헬스체크 연동
                     -> frontend 가 처음으로 (healthy) 를 찍는다
```

---

## 12. 관련 문서

| 문서 | 내용 |
|---|---|
| [09-current-infrastructure.md](09-current-infrastructure.md) | 현재 구조 실측 |
| [07-runbook-data-loading.md](07-runbook-data-loading.md) | 적재 절차 |
| [08-runbook-container-images.md](08-runbook-container-images.md) | 이미지 빌드·배포 |
| [05-data-and-deployment.md](05-data-and-deployment.md) | 환경변수 전체 표 |
