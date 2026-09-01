# Terraform 사전 결정사항 체크리스트

갱신일: 2026-09-01 · 원본 작성일: 2026-08-31

목표: 실제 프로젝트 아키텍처를 Terraform 으로 구축하기 전에 모듈 경계, 관리 주체,
네트워크, 보안, State 및 서비스 설정을 확정한다.

> 이 문서는 구현 코드가 아니라 **설계 결정 체크리스트**다. 각 모듈을 시작하기 전에
> 해당 항목을 확정하고, 선택 근거를 최종 구축 문서에 남긴다.

**설계 근거는 별도 문서에 있다.** 이 체크리스트는 "무엇을 정했나"이고, "왜 그렇게
정했나"는 [11-target-architecture.md](11-target-architecture.md) 를 본다. 현재
상태 실측은 [09](09-current-infrastructure.md), 이전 결정 이력은
[10](10-aws-deployment-design.md) 이다.

---

## 0. 원본 체크리스트에서 바뀐 것

**먼저 이것부터 확인한다.** 아래 여덟은 원본과 다르다. 하나라도 원본이 맞다면
알려 달라 — 뒤의 결정들이 여기에 딸려 있다.

| 항목 | 원본 | **갱신** | 근거 |
|---|---|---|---|
| 리전 | `us-east-2` 오하이오 | **`ap-northeast-2` 서울** | 세션 결정 |
| AZ | 2개 | **3개** `a`·`b`·`c` | **AmazonMQ 클러스터가 3 AZ 를 요구한다** |
| 환경 | `prod` 만 | **`dev` / `prod`** | 세션 결정 |
| Public Subnet | 2개 유지 (ALB·Bastion) | **없음** | Regional NAT + VPC Origin + SSM 이면 공인 IP 가 불필요 |
| Bastion | Elastic IP + 제한 SSH | **Private, SSM 전용** | public subnet 이 없어졌다 |
| 이미지 저장소 | EFS 로 통합, X-ray S3 폐기 | **EFS + X-ray S3 둘 다** | 담는 것이 다르다 (§8-1, §9) |
| State | Main State 1개 | **환경별 1개씩** | `dev`/`prod` 분리 |
| RDS | `db.t3.small` | **`db.t3.medium`** | 세션 결정 |

**원본에서 그대로 가져온 것**: 프로젝트/환경 이름, Naming 규칙, 공통 Tag, 단계별
구축·검증 루프, 모듈 구조, 문서화 템플릿, 보안 기본값. 이 부분들은 손대지 않았다.

---

## 1. 현재까지 확정된 사항

| 항목 | 결정 |
|---|---|
| 프로젝트 이름 | `emr-platform` |
| 환경 이름 | `dev`, `prod` |
| 기본 리전 | 서울 `ap-northeast-2` |
| 가용 영역 | `ap-northeast-2a`, `2b`, `2c` |
| VPC CIDR | `prod 10.0.0.0/16` · `dev 10.1.0.0/16` |
| Subnet | **Public 없음.** Private App `/24` 3개, Private Data `/24` 3개 |
| CloudFront 인증서/WAF 리전 | 버지니아 북부 `us-east-1` Provider Alias |
| NAT Gateway | VPC 단위 Regional NAT Gateway 1개, Automatic Mode |
| EKS 생성 | Bastion 에서 `eksctl` 로 별도 생성 |
| EKS 네트워크 | Terraform VPC 의 Private App Subnet 사용 |
| EKS Endpoint | **완전 Private** |
| EKS Node ASG | eksctl Managed Node Group 이 관리 |
| Node Group | `general` t3.medium 2~4 · **`ai` c6i.xlarge 1~2** |
| ALB/Target Group | AWS Load Balancer Controller 가 생성·관리 |
| ALB 배치 | Gateway API 로 3 AZ Private App Subnet 에 Internal ALB |
| ALB 대상 | `ip` Target Type 으로 EKS Pod 등록 |
| CloudFront Origin | Private ALB 를 VPC Origin 으로 사용 |
| 이미지 저장소 | **EFS**(진료 업로드) + **X-ray S3**(추론 산출물) |
| S3 구축 범위 | **로그 수집용 + X-ray 용 2개** |
| RDS | Terraform `30-data` 모듈로 구축 |
| 시크릿 주입 | **External Secrets Operator** |
| 컨테이너 레지스트리 | **GHCR (private)** |
| CD | **ArgoCD** — helm 1회 설치 후 자기 관리 |
| 백업 | RDS 자동 백업 7일 · **AWS Backup**(EBS) 7일 |
| Main State | 환경별 S3 State 1개씩 |
| Bootstrap State | `00-bootstrap/terraform.tfstate` 로컬 별도 State |
| 구축 방식 | 모듈을 하나씩 Root 에 추가해 `plan → apply → No changes` 확인 |
| 우선 구축 대상 | 기반 의존성 직후 Bastion EC2 |
| 최종 구축 대상 | CloudFront VPC Origin, CDN, WAF Association |

---

## 2. 프로젝트 공통 기준

### 1. 프로젝트 이름

- [x] `emr-platform`

### 2. 환경 이름

- [x] `dev`, `prod` — **VPC 부터 분리**

> **환경 둘은 비용이 두 배다.** 클러스터·RDS·NAT 가 각각 하나씩 더 든다. `dev` 는
> RDS 단일 AZ·작은 노드로 줄인다.

### 3. 공통 Naming 규칙

- [x] `<project>-<environment>-<resource>`

```text
emr-platform-prod-vpc
emr-platform-prod-alb
emr-platform-prod-efs
emr-platform-prod-logs
```

### 4. 공통 Tag

- [x] 모든 Terraform 리소스에 적용

```hcl
Project     = "emr-platform"
Environment = "prod"
ManagedBy   = "Terraform"
Team        = "AWS4"
```

### 5. 신규 생성 또는 기존 리소스 Import

- [x] 모든 프로젝트 리소스를 신규 생성

---

## 3. Network 결정사항

### 6. 사용할 AZ

- [x] `ap-northeast-2a`, `ap-northeast-2b`, `ap-northeast-2c`

**AZ 를 3개로 둔 이유는 AmazonMQ 다.** RabbitMQ 클러스터 배포는 노드 3개를 서로
다른 AZ 3곳에 둔다. EKS 자체는 2개면 되지만 MQ 가 3개를 요구한다.

`c6i.xlarge` 가 세 AZ 전부에서 쓸 수 있음을 계정에서 확인했다. 다른 계정·리전으로
옮길 때는 다시 확인한다.

```bash
aws ec2 describe-instance-type-offerings --location-type availability-zone \
  --filters Name=instance-type,Values=c6i.xlarge --region ap-northeast-2 \
  --query 'InstanceTypeOfferings[].Location' --output text
```

### 7. VPC CIDR

- [x] `prod` `10.0.0.0/16` · `dev` `10.1.0.0/16`

### 8. Subnet CIDR

- [x] **Public Subnet 없음.** 환경당 6개

| AZ | 용도 | prod | dev |
|---|---|---|---|
| a | Private App/EKS | `10.0.10.0/24` | `10.1.10.0/24` |
| b | Private App/EKS | `10.0.11.0/24` | `10.1.11.0/24` |
| c | Private App/EKS | `10.0.12.0/24` | `10.1.12.0/24` |
| a | Private Data | `10.0.20.0/24` | `10.1.20.0/24` |
| b | Private Data | `10.0.21.0/24` | `10.1.21.0/24` |
| c | Private Data | `10.0.22.0/24` | `10.1.22.0/24` |

`10.0.0.0/24`~`10.0.9.0/24` 는 향후 Public Subnet 이 필요해질 때를 위해 비워 둔다.
**서브넷은 추가할 수 있고 크기만 못 바꾼다.**

향후 연결할 GCP VPC 와 Private Service Access 대역은 `10.0.0.0/16`·`10.1.0.0/16`
과 겹치지 않게 설계한다.

**Data 를 별도 Subnet 으로 뺀 이유가 `/24` 때문이다.** VPC CNI 는 **파드마다 VPC
IP 를 할당**한다 — IP 를 먹는 것은 노드 수가 아니라 파드 수다. RDS·ElastiCache 가
같은 서브넷에 있으면 그만큼 파드 몫이 준다.

`/24` 는 AWS 예약 5개를 빼고 **251개**다. `t3.medium` 노드 하나가 ENI 3개 × 6 IP
로 약 17개를 잡는다. 지금 파드 25~40개에는 충분하다.

> **VPC CNI prefix delegation 을 켜지 않는다.** ENI 마다 `/28`(16개)을 통째로 잡아
> 이 계산이 깨진다.

### 9. Public Subnet 을 만들지 않는 근거

- [x] Public Subnet 미생성

원본은 "Regional NAT 자체에는 Public Subnet 이 필요 없지만 인터넷 공개 ALB 와
Bastion 배치를 위해 유지한다"였다. **그 둘이 모두 사라졌다.**

```
ALB       Private   CloudFront VPC Origin 이 직접 닿는다 (§30)
Bastion   Private   SSM Session Manager — 인바운드도 공인 IP 도 불필요 (§13)
NAT       서브넷 밖  Regional NAT 은 VPC 단위 자원
IGW       VPC 에 부착만  라우팅 테이블에 넣지 않는다
```

**공인 IP 를 가진 자원이 하나도 없다.**

### 10. NAT Gateway

- [x] VPC 단위 Regional NAT Gateway 1개
- [x] Automatic Mode
- [ ] Manual Mode — 현재 사용하지 않음

```hcl
resource "aws_nat_gateway" "regional" {
  vpc_id            = aws_vpc.main.id
  availability_mode = "regional"
}
```

Automatic Mode 에서는 `subnet_id`, `allocation_id`, `availability_zone_address` 를
지정하지 않는다. 세 AZ 의 Private App Subnet Route Table 이 **동일한 Regional NAT
Gateway ID** 를 기본 경로 대상으로 쓴다.

```hcl
version = ">= 6.24.0, < 7.0.0"
```

**주의할 점 둘.** Automatic Mode 는 스케일 다운·재확장 때 **egress IP 가 바뀐다.**
그리고 확장에 **최대 60분**이 걸리며 그동안 교차 AZ 트래픽이 생길 수 있다.

지금 밖으로 나가는 곳은 **상류 LLM API 와 GHCR 뿐이고 둘 다 허용목록이 없으므로**
Automatic Mode 로 충분하다. 외부가 우리 IP 를 허용목록에 넣어야 하는 요구가 생기면
Manual Mode 로 EIP 를 고정한다.

**IGW 는 필수다.** Regional NAT 과 CloudFront VPC Origin 이 각각 "이 VPC 가
인터넷과 통할 수 있다"는 표시로 IGW 를 요구한다. Public Subnet 이 없어도 VPC 에
부착만 하면 된다.

### 11. Data Subnet 인터넷 경로

- [x] 기본 인터넷 경로 없음

### 12. VPC Endpoint

- [x] Terraform `10-network` 범위에 포함
- [x] S3 Gateway Endpoint 1개 — Private App/Data Route Table 연결
- [x] `ssm` Interface Endpoint
- [x] `ssmmessages` Interface Endpoint
- [x] `ec2messages` Interface Endpoint
- [ ] ECR API / ECR DKR Interface Endpoint
- [ ] STS Interface Endpoint
- [ ] CloudWatch Logs Interface Endpoint

**Public Subnet 이 없어져 Bastion 도 Private 에 있다.** SSM 접속에는
`ssm`·`ssmmessages`·`ec2messages` 세 엔드포인트가 필요하다(원본은 두 개만 잡았다).
Regional NAT 으로도 되지만 엔드포인트가 더 좁고 안정적이다.

- [x] Endpoint 를 Private App Subnet 3 AZ 에 배치, Private DNS 활성화
- [x] Endpoint Security Group 은 Bastion SG 에서 오는 HTTPS TCP 443 만 허용

**ECR 엔드포인트는 만들지 않는다** — 레지스트리가 GHCR 이라 어차피 NAT 를 탄다
(§레지스트리). ECR 로 옮기면 그때 추가한다.

Interface Endpoint 는 시간당 비용이 있으므로 필요한 것만 만든다.

### 13. EKS Subnet Tag

- [x] Private App Subnet Tag 적용

```text
kubernetes.io/role/internal-elb = 1
```

**Public Subnet 이 없으므로 `kubernetes.io/role/elb` 태그도 없다.** ALB 가 항상
internal 이다.

> **eksctl 은 기존 서브넷에 태그를 추가하지 않는다.** 서브넷 소유자가 Terraform
> 이므로 태그도 Terraform 몫이다. 빠뜨리면 LB Controller 가 서브넷을 못 찾고,
> **클러스터를 다 만든 뒤 Gateway 가 안 뜨는 형태로** 드러난다.

---

## 4. Bastion 과 EKS 결정사항

### 14. Bastion 접근 방법

- [x] **SSM Session Manager 전용**
- [x] Private Subnet 배치
- [x] 인바운드 SG 규칙 없음
- [ ] ~~팀원별 공인 IP `/32` SSH 허용~~ — Public Subnet 이 없어 해당 없음
- [ ] ~~Elastic IP~~ — 해당 없음

원본은 SSM 과 제한된 SSH 를 병행했다. **Public Subnet 을 없애면서 SSH 경로 자체가
사라졌다.** 인바운드 규칙이 하나도 없으므로 IP 허용목록 관리도 필요 없다.

VS Code Remote 가 필요하면 **SSM 포트포워드**로 붙는다.

```bash
aws ssm start-session --target <instance-id> \
  --document-name AWS-StartPortForwardingSession \
  --parameters 'portNumber=22,localPortNumber=2222'
```

### 15. Bastion 사양

- [x] 확정

```text
Amazon Linux 2023
t3.medium
gp3 20GB
```

### 16. Bastion User data 도구

- [x] AWS CLI · kubectl · Helm · eksctl · Git · jq
- [x] SSM Agent 설치 상태 확인 및 서비스 활성화

User data 는 도구만 설치한다. `eksctl create cluster` 는 User data 에서 실행하지
않는다.

### 17. EKS 구축 주체

- [x] Bastion 에서 `eksctl` 로 EKS Cluster 와 Managed Node Group 생성·관리
- [x] Terraform 은 VPC, Private App Subnet, Route, NAT 및 보안 기반까지만 제공

EKS Cluster 와 Managed Node Group 은 **Terraform State 에 포함되지 않는다.**

**Terraform 에 `kubernetes`/`helm` Provider 를 넣지 않는다.** 넣는 순간 "존재하지
않는 클러스터를 참조하는 plan" 순환이 생긴다.

### 18. EKS Cluster 이름

- [x] `emr-platform-prod-eks` / `emr-platform-dev-eks`

### 19. EKS Kubernetes 버전

- [ ] 구축 시점 지원 버전 확인 후 확정

```bash
eksctl utils describe-cluster-versions
```

### 20. EKS Endpoint 접근

- [x] **완전 Private Cluster**
- [ ] ~~Public Access + 관리자 CIDR 제한~~

```yaml
privateCluster:
  enabled: true
  skipEndpointCreation: true    # Terraform 이 이미 만들었다
```

`skipEndpointCreation: true` 가 중요하다. eksctl 의 `privateCluster` 는 **자기가
VPC 를 만들 때만** 엔드포인트를 함께 만든다. 기존 VPC 를 넘기면 못 하므로 Terraform
이 만든 것을 쓰게 한다.

`kubectl` 접근은 Bastion 에서 한다.

### 21. Managed Node Group

- [x] 두 그룹으로 분리

| 그룹 | Instance Type | Min | Desired | Max | 워크로드 |
|---|---|---|---|---|---|
| `general` | `t3.medium` | 2 | 2 | 4 | frontend, spring-boot, 경량 API 4개, ArangoDB |
| `ai` | `c6i.xlarge` | 1 | 1 | 2 | xraygraph |

- [ ] Volume Size 확정

**`ai` 만 c 계열인 이유가 둘이다.**

**t3 는 버스터블이다.** CPU 크레딧이 마르면 베이스라인 20% 로 떨어진다. 추론은
짧고 굵게 CPU 를 전부 쓰는 작업이라 크레딧이 빠르게 마르고, 마른 뒤 성능은 예측이
어렵다.

**코어 수가 성능을 직접 정한다.** 실측이 14코어에서 3~4초였다.

```
14 vCPU (실측)        3~4초
 4 vCPU (c6i.xlarge)  10~12초 예상
 2 vCPU (t3.medium)   20~30초 예상 + 크레딧 소진 시 그 이상
```

웹 타임아웃이 60초라 실패하지는 않지만, 20초를 넘기면 사용자는 화면이 멈춘 것으로
느낀다. **taint/toleration 으로 두 그룹을 가른다.**

### 22. AWS Load Balancer Controller

- [x] EKS 생성 후 Helm 설치
- [x] **IRSA 사용** — eksctl `wellKnownPolicies.awsLoadBalancerController`
- [x] **v2.13 이상** — Gateway API 지원 최소 버전

Node Role 에 ALB 권한을 직접 추가하지 않는다.

### 23. EKS와 Terraform 삭제 순서

- [x] 삭제 절차 문서화

```text
Kubernetes Gateway, HTTPRoute, Service 삭제
→ AWS Load Balancer Controller 가 생성한 ALB/Target Group 삭제 확인
→ CloudFront VPC Origin 삭제
→ eksctl delete cluster
→ terraform destroy
```

EKS 보다 Terraform 네트워크를 먼저 삭제하면 ENI, Load Balancer, 보안 그룹 의존성
때문에 VPC/Subnet 삭제가 **오래 매달린 뒤 실패한다.**

---

## 5. ALB 와 EKS 연결 결정사항

### 24. ALB Scheme 과 배치

- [x] `internal` — Gateway API 에서 설정
- [x] Private App Subnet 3 AZ 에 배치
- [x] CloudFront VPC Origin 을 통해서만 접근

### 25. Target Group Target Type

- [x] `ip` — EKS Pod 직접 등록

### 26. Target 등록 주체

- [x] AWS Load Balancer Controller 가 ALB·Target Group 생성 및 Pod 등록·해제

### 27. 애플리케이션 포트

- [x] 확정

| 서비스 | 포트 |
|---|---|
| frontend | `3000` |
| spring-boot | `8080` |
| prescription-api | `8001` |
| validation-agent | `8002` |
| llm-gateway | `8003` |
| certificate-api | `5001` |
| xraygraph | `8000` |
| flask-radiology | `5000` |

**ALB 가 노출하는 것은 frontend·spring-boot·xraygraph 셋뿐이다.** 나머지는
ClusterIP 로 클러스터 내부에서만 접근한다.

### 28. Health Check 경로

- [x] 확정

| 서비스 | 경로 |
|---|---|
| frontend | `/api/health` |
| spring-boot | `/actuator/health` |
| 파이썬 서비스 | `/health` |
| flask-radiology | `/api/ai/is_running` |

> **frontend `/api/health` 는 새로 만든 것이다.** 없으면 `readinessProbe` 가
> 컨테이너 프로세스만 보고 트래픽을 보내, Next 가 준비되기 전 요청이 실패한다.
> 상류(Spring·DB)는 확인하지 않는다 — 상류 장애가 이 파드 재시작으로 번지면 안 된다.

### 29. ALB Listener

- [x] Ingress 대신 Kubernetes Gateway API 사용
- [x] **Gateway API CRD 를 따로 설치한다** — 쿠버네티스에 내장돼 있지 않다
- [x] 인증서·스킴 같은 ALB 고유 설정은 `LoadBalancerConfiguration` CRD 로 붙인다
- [ ] Listener 프로토콜과 인증서는 EKS 구축 시 확정
- [ ] CloudFront → Private ALB 구간의 HTTP/HTTPS 여부는 Edge 구축 시 확정

### 30. Gateway API 경로 라우팅

- [x] `/*` → frontend
- [x] `/api/*` → spring-boot
- [x] **`/storage/*` → xraygraph**

**`/storage/*` 를 빠뜨리면 안 된다.** `xraygraph` 는 다른 내부 서비스와 달리
**브라우저가 직접 읽는 경로를 갖는다.**

```python
app.mount("/storage", StaticFiles(directory=STORAGE_DIR), name="storage")
```

추론 응답의 `heatmapPath` 를 Spring 이 절대 URL 로 만들어 브라우저에 주고, 브라우저가
그 주소로 히트맵 PNG 를 가져간다. **ClusterIP 로만 두면 분석은 되는데 이미지가 안
뜬다.**

네임스페이스를 넘는 Backend 참조가 필요하면 `ReferenceGrant` 를 추가한다.

### 31. ALB 직접 접근 차단

- [x] Internal Scheme + Private App Subnet
- [x] CloudFront VPC Origin 을 유일한 외부 진입 경로로 사용
- [x] VPC Origin 생성 후 AWS 가 만드는 Service-managed Security Group 으로 인바운드 제한

**CloudFront VPC Origin 은 `ap-northeast-2` 에서 지원된다.** AZ 예외도 없다.

요구사항 셋을 지킨다.

```
IGW      VPC 에 부착돼 있어야 한다        Regional NAT 도 요구하므로 어차피 있다
ALB SG   보안 그룹이 붙어 있어야 한다
NACL     인바운드는 평가되지 않는다        아웃바운드가 ephemeral(1024-65535)을 허용해야 한다
```

SG 인바운드는 둘 중 하나로 연다.

| | 방법 | 시점 |
|---|---|---|
| A | CloudFront 관리형 Prefix List | 오리진 생성 **전에도** 가능 |
| B | Service-managed SG `CloudFront-VPCOrigins-Service-SG` | 오리진 생성 **후에만** |

**B 가 더 좁다.** 이름이 `CloudFront-VPCOrigins-Service-SG` 로 시작하는 SG 를 직접
만들지 않는다 — AWS 예약 패턴이다.

> gRPC 와 Lambda@Edge 오리진 트리거는 VPC Origin 에서 지원되지 않는다. 둘 다
> 우리와 무관하다.

---

## 6. CloudFront 결정사항

### 32. CloudFront Behavior

- [x] 기본 `/*` → VPC Origin → Private ALB
- [ ] `/_next/static/*` 장기 캐시 Behavior 검토 — 파일명에 해시가 있어 무효화 불필요

### 33. Custom Domain

- [ ] 보유 도메인 사용
- [ ] Route 53 Hosted Zone
- [x] **CloudFront 기본 도메인 사용** — Route53 은 나중 단계

**단일 오리진이라 CORS·SameSite 재설계가 필요 없다.** 프론트와 API 가 같은
CloudFront 도메인 아래 있고, 인증이 쿠키 기반이라 이 이득이 크다.

`NEXT_PUBLIC_API_BASE_URL` 은 빈 값 + 상대 경로로 두면 **도메인이 바뀌어도 재빌드가
필요 없다.**

### 34. 인증서

- [ ] CloudFront 인증서: `us-east-1` — Custom Domain 붙일 때
- [ ] ALB 인증서: `ap-northeast-2` — CloudFront→ALB 를 HTTPS 로 할 때

### 35. Cache Policy

- [ ] ALB Origin 동적 응답 캐시 비활성 또는 최소화
- [ ] API Query/Header/Cookie 전달 항목 확정

**쿠키를 반드시 전달해야 한다** — 인증이 쿠키 기반이다.

### 36. SPA 여부

- [x] **해당 없음** — Next.js SSR 컨테이너다. 정적 사이트가 아니다

원본의 "403/404 를 `/index.html` 로" 는 정적 호스팅 전제였다. **정적 export 가
불가능하다** — `middleware.ts` 와 API Route 둘이 있어 Next 정적 export 가 지원하지
않는다.

### 37. CloudFront Price Class

- [ ] 추후 결정

---

## 7. WAF 결정사항

### 38. WAF 연결 위치

- [x] **CloudFront 에만 연결** (`us-east-1` 스코프)
- [ ] ALB 에는 별도 WAF 없음

ALB 가 Private 이고 CloudFront 만이 유일한 진입 경로이므로 우회 경로가 없다.

### 39. AWS Managed Rule

- [ ] Common Rule Set
- [ ] Known Bad Inputs
- [ ] Amazon IP Reputation
- [ ] Anonymous IP List

### 40. Rate Limit

- [ ] 기준 확정

### 41. WAF Log

- [ ] 로그 수집용 S3 전달 구조 확정
- [ ] Firehose 필요 여부 확인

### 42. 초기 동작 모드

- [ ] Count 로 검증 후 Block 전환 — 권장

---

## 8. RDS 결정사항

### RDS-1. 구축 주체와 네트워크

- [x] Terraform `30-data` 모듈로 구축
- [x] Private Data Subnet 3 AZ 로 DB Subnet Group 구성
- [x] Public Access 비활성화
- [x] RDS SG 는 EKS 애플리케이션 SG 에서만 DB 포트 허용

> **SG 순환 참조를 피한다.** 클러스터 SG 는 eksctl 이 만들고 RDS SG 는 Terraform 이
> 만든다. Terraform 이 클러스터 SG ID 를 참조하면 순환이 생기므로 **소스를 Private
> App Subnet CIDR 로 준다.**

### RDS-2. 데이터베이스 사양

- [x] Engine: MySQL
- [ ] **버전 확정 필요 — 아래 참조**
- [x] Instance Class: `db.t3.medium`
- [x] Storage Type: `gp3`
- [x] Initial Storage: `20 GiB`
- [x] Storage Autoscaling Maximum: `100 GiB`
- [x] Multi-AZ 활성화
- [x] Database Name: `bitcomputer`
- [x] Master Username: `emr_admin`

> **버전 파리티 문제가 있다.** 로컬 compose 는 `mysql:8`(8.0.x)이고 원본
> 체크리스트는 8.4 LTS 다. **다른 엔진으로 테스트하는 셈이 된다.**
>
> | | 8.0 | 8.4 LTS |
> |---|---|---|
> | 로컬과 일치 | O | **compose 도 함께 올려야 한다** |
> | 지원 기간 | 짧다 | 길다 |
>
> **8.4 로 가되 `infra/docker-compose.yml` 의 `mysql:8` 도 `mysql:8.4` 로 올리는
> 것을 권한다.** 로컬과 프로덕션 엔진이 갈리면 "로컬에서는 되는데" 가 나온다.

- [ ] 구축 직전 `ap-northeast-2` 지원 최신 Minor Version 확인·고정

**`bitcomputer` 는 로컬 `MYSQL_DATABASE` 와 같은 이름이다.** 적재 스크립트가 이
이름을 본다.

### RDS-3. 데이터 보호

- [x] 저장 데이터 암호화 활성화
- [x] RDS 전용 고객 관리형 KMS Key 생성
- [x] KMS Alias: `alias/emr-platform-prod-rds`
- [x] KMS Automatic Key Rotation 활성화
- [x] Automated Backup Retention: **7일**
- [x] Deletion Protection 활성화
- [x] Final Snapshot 생성: `skip_final_snapshot = false`
- [x] `prevent_destroy` 적용
- [ ] Final Snapshot Identifier 충돌 방지 규칙은 구현 시 확정
- [x] CloudWatch Log Export: `error`, `slowquery`
- [x] Custom DB Parameter Group 생성
- [x] `slow_query_log = 1`, `log_output = FILE`
- [x] `long_query_time` 기본값 `10초` 사용

### RDS-4. 자격 증명

- [x] 관리형 Master User Password: `manage_master_user_password = true`
- [x] AWS Secrets Manager 에 자동 생성·저장
- [x] Terraform 코드와 `tfvars` 에 평문 비밀번호 저장 금지
- [x] **EKS 워크로드 접근은 External Secrets Operator 로** (§72)

---

## 8-1. EFS 결정사항

### 43. 저장소 유형

- [x] EFS 를 Terraform `30-data` 범위에 포함
- [x] **진료 업로드 원본과 flask 오버레이만 EFS 에 둔다**
- [ ] ~~X-ray 이미지를 EFS 로 통합~~ — **철회. §9 참조**

원본은 X-ray 를 EFS 로 합치고 X-ray S3 를 없앴다. **담는 것이 다르다.**

```
EFS   images/<radiologyRequestId>/original/<파일명>              Spring 이 업로드를 저장
      images/<radiologyRequestId>/overlay/<파일명>_overlay.jpg   flask 가 히트맵을 얹어 저장
```

**EFS 여야 하는 이유는 ReadWriteMany 다.** Spring 과 flask 가 **같은 디렉터리를
각자 쓴다.** EBS 는 ReadWriteOnce 라 안 된다.

`RADIOLOGY_ENGINE=xray` 인 지금은 flask 가 호출되지 않아 실제로는 Spring 혼자
쓰지만, **flask 를 켜는 순간 조용히 깨진다.**

**용량은 작다.** X-ray 원본 1장 46KB. 단가가 S3 의 10배여도 이 규모에서 절대 금액
차이가 무의미하다.

> **뒤집을 조건:** 업로드가 수십 GB 를 넘거나 Spring 의 정적 서빙(`/images/**`)을
> CloudFront 로 옮길 때. 그때는 S3 로 간다.

### 44. EFS 네트워크

- [x] Private App Subnet 3 AZ 에 Mount Target 생성
- [x] EFS SG 의 NFS TCP 2049 를 EKS 에서만 허용

### 45. EFS 암호화

- [x] 저장 데이터 암호화 활성화
- [ ] AWS 관리형 키 / 고객 관리형 KMS 키 선택

### 46. EFS 성능과 Lifecycle

- [ ] Throughput Mode
- [ ] Performance Mode
- [ ] IA 전환 기간

### 47. EKS 마운트 방식

- [x] EFS CSI Driver 설치 — eksctl IRSA
- [ ] EFS Access Point 생성
- [ ] StorageClass/PVC 작성
- [ ] Pod Mount Path 확정

**Mount Path 는 컨테이너마다 다르다.** 지금 compose 기준이다.

```
spring-boot       /app/BitComputer/images
flask-radiology   /app/Back-End/BitComputer/images
```

> **이전 전에 고쳐야 할 코드가 있다.** `ImageStorageUtil.getProjectRoot()` 와
> `WebMvcConfig` 가 작업 디렉터리에서 `BitComputer` 폴더를 위로 훑어 찾고, 못 찾으면
> **현재 디렉터리에 만든다.** `image.storage.path` 프로퍼티가 이미 있는데 무시한다.
> K8s 에서 다른 곳을 가리키면 예외가 아니라 **빈 디렉터리를 만들고 정상처럼 뜬다.**

### 48. 백업

- [x] AWS Backup 적용
- [x] 보존 기간 **7일**

### 49. 애플리케이션 접근 경계

- [x] EKS 워크로드만 EFS 에 접근
- [x] EFS 는 CloudFront Origin 으로 사용하지 않음
- [x] 이미지는 애플리케이션/ALB 경로를 통해 제공

---

## 9. S3 결정사항

**S3 를 2개 만든다.** 원본은 로그용 1개만 두고 X-ray 를 EFS 로 합쳤는데, X-ray
산출물은 성격이 다르다.

### 50. X-ray S3

- [x] Terraform `30-data` 범위에 포함

`xraygraph` 의 `storage/` 다. **진료 데이터가 아니라 CheXpert 사례와 추론
산출물이다.**

| 종류 | 접두사 | 언제 생기나 | 실측 |
|---|---|---|---|
| 사례 원본 | `case_*` | 적재 시 1회 | 471개 · 26MB |
| 재구성 출력 | `case_*` | 적재 시 1회 | 471개 · 19MB |
| 히트맵 | `case_*` | 적재 시 1회 | 471개 · 65MB |
| **질의 히트맵** | `query_case_*` | **추론할 때마다 1개** | 누적 |

**질의 히트맵이 무한히 쌓인다.** 추론 한 번에 파일 하나다. **라이프사이클로 자동
만료시킬 수 있다는 것이 EFS 대신 S3 를 쓸 실질 근거다.**

- [x] SQUID 모델 가중치 보관 — `models/squid_exp1_256_mask/model.pth`
- [ ] `query_case_*` 만료 기간 확정

**이관을 두 단계로 나눈다.**

```
1단계   적재 산출물만 S3 에 백업 (재적재에 4.5분 걸린다)
        질의 히트맵은 EBS 에 두고 /storage/* HTTPRoute 로 서빙

2단계   히트맵을 S3 에 직접 쓰고 CloudFront 가 서빙
        xraygraph 의 StaticFiles 마운트와 /storage/* 라우트를 함께 제거
```

### 51. 로그 수집용 S3

- [x] Terraform `30-data` 범위에 포함
- [ ] CloudFront Access Log
- [ ] WAF Log
- [ ] ALB Access Log
- [ ] Application Log
- [ ] CloudTrail

> **모니터링·알람·옵저버빌리티는 이번 범위가 아니다.** 버킷은 만들되 수집
> 파이프라인은 나중에 붙인다.

### 52. 로그 보관 기간

- [ ] 확정

```text
30일 Standard → 90일 후 Glacier → 1년 후 삭제
```

### 53. 로그 Prefix

```text
cloudfront/
waf/
alb/
application/
```

### 54. 버킷 보안

- [x] Public Access 차단 (두 버킷 모두)
- [ ] 필요한 AWS Service Principal 만 Bucket Policy 에서 허용
- [ ] Object Lock 필요 여부 검토

---

## 10. Redis 결정사항

### 55. Redis 구성

- [x] ElastiCache Replication Group
- [ ] Cluster Mode 사용 여부 확정

### 56. Multi-AZ 와 Replica

- [ ] Primary 1 + Replica 1, Multi-AZ
- [ ] Single Node 비용 절감 구성

**용도가 세션·캐시뿐이다.** 유실돼도 재로그인으로 회복되므로 `dev` 는 Single Node
로 충분하다.

### 57. Node Type

- [x] `cache.t3.medium`

### 58. Redis 인증

- [ ] AUTH Token
- [ ] TLS
- [x] Secrets Manager 저장 → **ESO 로 파드에 주입**

### 59. Backup

- [ ] Snapshot Retention
- [ ] Maintenance Window
- [ ] Automatic Failover

### 60. Redis 접근 주체

- [x] EKS 애플리케이션 SG 에서만 허용

---

## 11. Amazon MQ 결정사항

### 61. MQ 엔진

- [x] **RabbitMQ**

### 62. 배포 모드

- [x] **Cluster Deployment** — 노드 3개 × 3 AZ

### 63. Instance Type

- [x] `mq.m7g.medium` × 3

**`mq.t3.micro` 는 선택지가 아니다.** 신규 생성이 이미 막혔고 **지원 종료가
2026-10-01** 이며 클러스터도 지원하지 않는다.

```
클러스터 최소   mq.m7g.medium  (1 vCPU / 4GB, "Evaluation" 등급)
프로덕션 권장   mq.m7g.large   (2 vCPU / 8GB)
```

> **비용을 보고 되돌릴 수 있는 결정이다.** 클러스터는 브로커 3대다. 이 프로젝트
> 부하(사용자 클릭당 job 하나)에는 Single Instance 로도 충분하다.

### 64. 엔진 버전

- [x] **RabbitMQ 4.2**

```
RabbitMQ 4.2    mq.m7g 에서만 지원 — 최신, AWS 권장
RabbitMQ 3.13   mq.t3 / mq.m5 / mq.m7g 전부
```

로컬은 `rabbitmq:3-management` 다. `m7g` + `4.2` 조합이 자연스럽다.

> **AmazonMQ 는 streams 를 지원하지 않는다** — 만들면 데이터 손실이다. JSON 구조화
> 로깅도 안 된다. 우리는 일반 큐만 쓰므로 걸리지 않는다.

### 65. 인증 정보

- [x] Secrets Manager 저장 → **ESO 로 파드에 주입**
- [x] 코드와 tfvars 에 평문 저장 금지

### 66. 접근 포트

- [x] AMQP `5671` (TLS)

### 67. 접근 주체

- [x] EKS 애플리케이션 SG 에서만 허용

### 68. 로그

- [ ] CloudWatch Log 활성화

> **컨슈머 하트비트에 주의한다.** 로컬에서 RabbitMQ 하트비트 주기 두 번(120초)을
> 넘겨 브로커가 연결을 닫고 **같은 비싼 작업이 무한 재처리되던 결함**이 있었다
> (F-H7). `VALIDATION_JOB_BUDGET_SECONDS` 를 110초로 두어 막고 있다. AmazonMQ 로
> 옮겨도 이 값은 그대로 유지한다.

---

## 12. IAM, Secrets, KMS 결정사항

### 69. Terraform 실행용 IAM Role

- [ ] 구축 권한 범위 확정
- [x] AWS Root Access Key 사용 금지
- [x] GitHub Actions 는 **OIDC** — 장수명 키 없음

### 70. Bastion IAM Role

- [x] Bastion 전용 IAM Role 및 Instance Profile 을 Terraform 으로 생성·연결
- [x] AWS 액세스 키를 Bastion 에 저장하지 않음
- [x] EKS 생성·조회 권한
- [x] CloudFormation 권한
- [x] EC2/IAM 관련 eksctl 권한
- [x] SSM Session Manager 연결 권한
- [ ] 필요한 경우 ECR

### 71. EKS 관련 Role

- [x] Node Role — eksctl 관리
- [x] AWS Load Balancer Controller — **IRSA** (`wellKnownPolicies`)
- [x] EFS CSI Driver — **IRSA**
- [x] EBS CSI Driver — **IRSA**
- [x] External Secrets Operator — **IRSA**

`eksctl` 의 `wellKnownPolicies` 를 쓰면 OIDC 공급자·신뢰 정책·역할·정책 연결·
ServiceAccount 애노테이션이 한 번에 붙는다.

### 72. Secret 관리 — External Secrets Operator

- [x] **ESO 로 Secrets Manager 를 K8s Secret 으로 동기화**

```
Secrets Manager
   │  ClusterSecretStore (IRSA — 정적 키 없음)
   ▼
ExternalSecret  →  K8s Secret  →  파드 envFrom
```

**이 선택의 근거는 하나다 — 이 앱들은 전부 환경변수로 설정을 읽는다**(`.env` 37개
키). ESO 는 코드 수정이 0 이다. Secrets Store CSI 는 파일 마운트라 환경변수로
쓰려면 결국 Secret 을 또 만들어야 하고, IRSA 직접 호출은 8개 서비스를 전부 고쳐야
한다.

관리 대상:

- [x] RDS Master Password (RDS 가 자동 생성)
- [x] Redis AUTH Token
- [x] MQ 사용자 비밀번호
- [x] `LLM_API_KEY` — 상류 LLM 자격증명
- [x] `JWT_SECRET`
- [x] `ARANGO_PASSWORD`
- [x] **GHCR 토큰** → `dockerconfigjson` 타입 Secret 으로 뿌린다

> **회전에는 재시작이 필요하다.** ESO 가 K8s Secret 은 갱신하지만 **파드의
> 환경변수는 기동 시점에 고정된다.** 자동화하려면 `stakater/Reloader` 를 얹는다.
> 지금 규모에서는 수동 롤링 재시작으로 충분하다.

### 73. KMS Key

- [x] RDS 전용 고객 관리형 Key
- [ ] EFS / S3 Key 분리 여부 확정

---

## 12-1. 컨테이너 레지스트리와 CD

### 74. 레지스트리

- [x] **GHCR (private)**

AWS 와 GCP DR 이 같은 이미지를 당겨간다. ECR 이면 클라우드마다 레지스트리를 두고
미러링해야 한다.

대가를 적어 둔다.

```
NAT 필수          ghcr.io 는 VPC 엔드포인트가 없다
imagePullSecret   private 이므로 이미지를 당기는 네임스페이스마다 필요
토큰 만료          PAT 를 쓰면 만료 관리가 따라온다
```

**뒤의 둘은 ESO 가 줄여 준다** — 토큰을 Secrets Manager 에 한 벌 두면 회전할 자리가
한 곳이 된다.

### 75. 이미지 태그

- [x] `sha-<커밋>` 불변 태그만 매니페스트가 참조
- [x] `main` 은 사람 확인용
- [x] **`latest` 를 만들지 않는다**

`latest` 를 쓰면 ArgoCD 가 "동기화됨"이라 하는데 파드는 다른 이미지인 상황이 나온다.

### 76. 경로 → 이미지 매핑

- [x] **1:1 이 아니다**

| 경로 | 이미지 |
|---|---|
| `services/prescription` | **prescription-api, certificate-api** ← 둘 |
| `apps/api` | spring-boot |
| `apps/web` | frontend |
| `services/validation-agent` | validation-agent |
| `services/llm-gateway` | llm-gateway |
| `services/xray-rag` | xraygraph |
| `services/radiology-legacy` | flask-radiology |

**매핑을 명시하지 않으면 `certificate-api` 가 조용히 낡는다.** 실제로 커밋 11개
뒤진 채 healthy 로 돌던 적이 있다.

### 77. CD — ArgoCD

- [x] **helm 1회 설치 후 자기 관리**

```
1. eksctl create cluster
2. helm install argocd argo/argo-cd -n argocd -f bootstrap/argocd-values.yaml
3. kubectl apply -f bootstrap/root-app.yaml        app-of-apps
4. 이후 ArgoCD 가 자기 자신을 포함해 전부 관리
```

> **자기 관리에는 위험이 있다.** 잘못된 sync 로 ArgoCD 가 죽으면 스스로 복구하지
> 못한다. `bootstrap/argocd-values.yaml` 을 레포에 남겨 helm install 로 되살린다.

- [x] 태그 갱신은 **CI 커밋** (Argo Image Updater 아님)
- [x] `dev` 자동 bump / `prod` 는 PR 프로모션
- [x] ArgoCD UI 는 외부 노출 없이 **Bastion 경유 SSM 포트포워드**

### 78. 레포 구성

```
bitcomputer-emr       앱 소스 + Dockerfile
bitcomputer-gitops    kustomize overlay, ArgoCD Application    ← ArgoCD 가 보는 곳
bitcomputer-infra     Terraform
```

**매니페스트를 별도 레포로 두는 이유**는 봇이 하루에 수십 번 태그 커밋을 쌓는데 앱
소스 히스토리에 섞이면 리뷰가 불가능해지기 때문이다. ArgoCD deploy key 범위도
매니페스트로 좁힐 수 있다.

**분리의 실체는 디렉터리가 아니라 크리덴셜이다.**

```
앱 CI      레지스트리 write + 매니페스트 write.  클러스터 접근 불가
인프라 CI   AWS OIDC.                          레지스트리 접근 불가
매니페스트   권한 없음. ArgoCD 가 read-only deploy key 로 pull
```

---

## 12-2. 데이터 적재

**적재도 GitOps 로 돈다.** CI 에 클러스터 크리덴셜을 주지 않기 위해서다.

```
엑셀 푸시 → ETL 실행 → etl 이미지 빌드(CSV 포함, sha 태그)
        → Job 매니페스트 bump(name: etl-load-<sha7>) → ArgoCD sync
        → Job 실행 → 건수 검증(다르면 실패)
```

**Job 이름에 sha 를 넣는다.** 그래야 데이터가 바뀔 때만 새 Job 객체가 생기고
ArgoCD 가 한 번만 실행한다. `ttlSecondsAfterFinished` 로 오래된 Job 을 정리한다.

### 79. 갱신이 필요한 저장소

| 대상 | 출처 | 트리거 |
|---|---|---|
| RDS `disease` / `diagnose` | 엑셀 2개 (50,941 / 505,954행) | 엑셀 푸시 |
| ArangoDB `bitcomputer_graph` | 엑셀 + 합성 케이스 | 엑셀 푸시 |
| ArangoDB `xray_graph_db` | CheXpert 202건 | 모델·마스크 변경 |

> **`import_to_arango.py` 는 기본이 truncate 다.** 원본 적재 후 `--append` 로 합성
> 케이스를 다시 넣어야 한다. 순서가 뒤바뀌면 합성 120건이 사라진다.

> **적재 Job 과 런타임 파드가 같은 ConfigMap 을 봐야 한다.** `USE_PSPNET_ROI` 가
> 코드와 compose 양쪽에 기본값을 갖는데 적재 스크립트가 compose 를 거치지 않아,
> **저장 코퍼스와 질의가 서로 다른 기준 위에 놓였는데 양쪽 다 정상으로 보인** 적이
> 있다. K8s 에서 같은 함정이 재발한다.

### 80. ArangoDB — 인클러스터

- [x] **AWS 관리형 등가물이 없다.** 인클러스터 + EBS
- [x] EBS CSI 동적 프로비저닝 (정적 PV 로 미리 만들지 않는다)
- [x] `topology.kubernetes.io/zone` 노드 어피니티 + `WaitForFirstConsumer`

**EBS 는 AZ 에 묶인다.** 노드 장애 시 같은 AZ 로 재스케줄되어야 한다.

### 81. SQUID 가중치 — initContainer

```
S3 models/squid_exp1_256_mask/model.pth
   │  initContainer — IRSA 인증, 체크섬 검증
   ▼
emptyDir /weights
   │
   ▼
xraygraph   SQUID_MODEL_DIR=/weights/squid_exp1_256_mask
```

지금은 `xraygraph` 가 `services/radiology-legacy` 디렉터리를 바인드 마운트해 읽는다.
**K8s 에는 그런 마운트가 없다.**

**체크섬을 검증한다.** 가중치가 바뀌었는데 이미지가 그대로면 `engineStatus` 는
여전히 `real` 인데 **모델이 다르다.**

### 82. 백업 — AWS Backup

- [x] RDS 자동 백업 7일
- [x] **ArangoDB EBS 볼륨 — AWS Backup 7일**

**볼륨 ID 를 Terraform 이 모른다.** PVC 가 동적으로 만들기 때문이다. **태그로
선택**한다.

```
StorageClass   tagSpecification 으로 볼륨에 backup=arangodb 를 붙인다
AWS Backup     그 태그를 selection 조건으로 쓴다
```

**StorageClass 쪽 태그를 빠뜨리면 백업 계획은 만들어지는데 대상이 0건이 된다** —
콘솔에서 계획이 초록으로 보이므로 복원할 때까지 모른다.

> **EBS 스냅샷은 crash-consistent 다.** ArangoDB 는 WAL 이 있어 대부분 복구되지만
> **복원을 한 번은 실제로 해 봐야 한다.**

**무엇이 복구되고 무엇이 안 되는지 구분해 둔다.**

| | 복구 경로 |
|---|---|
| 처방 그래프 원본 | 엑셀 → ETL 재적재 (4.5분) |
| 합성 케이스 | 스크립트 재실행 (결정론적) |
| X-ray 코퍼스 | CheXpert 재시드 (4.5분) |
| **운영 중 쌓인 피드백 이력** | **백업뿐이다** |

---

## 13. Terraform Backend 와 State 결정사항

### 83. State Bucket

- [x] `emr-platform-tfstate-<account-id>`
- [x] Region: `ap-northeast-2`

### 84. State Key

- [x] 환경별로 하나씩

```text
prod/main/terraform.tfstate
dev/main/terraform.tfstate
```

### 85. State Lock

- [x] S3 Native State Lock `use_lockfile = true` — DynamoDB 불필요

### 86. State 보호

- [x] Versioning 활성화
- [x] SSE-S3(`AES256`) 기본 암호화
- [x] Public Access Block 전체 활성화
- [x] `prevent_destroy` 적용
- [x] State 접근용 최소 IAM 권한

### 87. State 구조

- [x] Bootstrap State 는 `infra/00-bootstrap/terraform.tfstate` 로컬 별도 보관
- [x] Main State 는 **환경당 1개**

**모듈 번호는 State 경계가 아니라 코드 정리용이다.** `10-network`~`50-app` 이 하나의
State 안에 있고, Root Module 에 Child Module 을 하나씩 추가하며 apply 한다.

원본의 근거를 그대로 채택한다 — 동일 팀 소유, 강한 모듈 간 의존성, 짧은 구축 일정,
`terraform_remote_state` 연결 복잡도 방지. 향후 소유 팀과 변경 주기가 나뉘면 분리를
재검토한다.

Bootstrap State 는 Git 에 커밋하지 않는다.

---

## 14. 권장 모듈 구조

```text
infra/
├── 00-bootstrap/
│   ├── 10-state-bucket.tf
│   ├── 20-state-security.tf
│   ├── variables.tf
│   └── outputs.tf
│
├── environments/
│   ├── prod/
│   │   ├── 00-backend.tf
│   │   ├── 10-providers.tf        # ap-northeast-2 + us-east-1 alias
│   │   ├── 20-locals.tf
│   │   ├── 30-modules.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── terraform.tfvars.example
│   └── dev/
│       └── (동일 구조)
│
└── modules/
    ├── 10-network/
    │   ├── 10-vpc.tf
    │   ├── 20-subnets.tf          # private app ×3, private data ×3
    │   ├── 30-gateways.tf         # IGW, Regional NAT
    │   ├── 40-routes.tf
    │   ├── 50-endpoints.tf        # S3 gateway, ssm/ssmmessages/ec2messages
    │   ├── variables.tf
    │   └── outputs.tf
    │
    ├── 20-security/
    │   ├── 10-security-groups.tf
    │   ├── 20-iam.tf
    │   ├── 30-kms.tf
    │   ├── 40-acm.tf              # us-east-1 alias
    │   ├── 50-waf.tf              # us-east-1 alias, CloudFront 스코프
    │   ├── variables.tf
    │   └── outputs.tf
    │
    ├── 30-data/
    │   ├── 10-rds.tf
    │   ├── 20-efs.tf
    │   ├── 30-log-s3.tf
    │   ├── 35-xray-s3.tf          # 추가
    │   ├── 40-redis.tf
    │   ├── 50-amazon-mq.tf
    │   ├── 60-aws-backup.tf       # 추가
    │   ├── variables.tf
    │   └── outputs.tf
    │
    ├── 40-platform/
    │   ├── 10-bastion.tf
    │   ├── 20-cloudfront.tf       # VPC Origin 포함
    │   ├── 30-waf-association.tf
    │   ├── variables.tf
    │   └── outputs.tf
    │
    └── 50-app/
        └── README.md  # Terraform 리소스 없음. Kubernetes 리소스는 gitops 레포
```

Terraform 은 파일 이름 순서대로 실행하지 않고 의존성 Graph 를 계산한다. 숫자
접두사는 사람이 코드를 찾고 구축 순서를 이해하기 쉽게 만드는 용도다.

---

## 15. 구축 시작 준비 상태

### 아키텍처 결정 완료

- [x] 프로젝트·환경·리전·AZ 확정
- [x] VPC 및 6개 Subnet CIDR 확정 (**Public 없음**)
- [x] Regional NAT Gateway 와 VPC Endpoint 방향 확정
- [x] Terraform 과 eksctl/Kubernetes 의 관리 경계 확정
- [x] Private ALB 와 CloudFront VPC Origin 구성 확정 (**서울 지원 확인**)
- [x] Ingress 대신 Gateway API 사용 확정
- [x] **EFS(진료 업로드) + X-ray S3(추론 산출물) 분리 확정**
- [x] **Node Group 2개 분리 확정** (general / ai)
- [x] **시크릿 주입 기제 확정** (ESO)
- [x] **ArgoCD 부트스트랩 확정**
- [x] **레지스트리·태그 갱신 방식 확정** (GHCR private, CI 커밋)
- [x] **백업 확정** (RDS 7일, AWS Backup 7일)
- [x] Module 구조와 단계별 구축 순서 확정
- [x] State Bucket 이름·리전·Key·Lock·보호 설정 확정

### 실행 직전 준비값

- [ ] `ap-northeast-2` 에 임시 Terraform 작업 환경
- [ ] Terraform 실행용 IAM Role
- [ ] GitHub Actions OIDC Role (인프라 레포용)
- [ ] GHCR 토큰 (fine-grained PAT, `read:packages`)

**공용 EC2 Key Pair 와 팀원 공인 IP 목록은 더 이상 필요 없다** — Bastion 이 SSM
전용이 되면서 SSH 경로가 사라졌다.

### 이전 전에 고쳐야 할 애플리케이션 코드

- [ ] `ImageStorageUtil` / `WebMvcConfig` 경로 탐색 → `image.storage.path` 준수 **(필수)**
- [ ] `http/client.ts` 빈 `baseURL` → 상대 경로 (한 줄)
- [ ] `infra/docker-compose.yml` 의 `mysql:8` → RDS 버전과 맞추기

### 해당 모듈 구축 시 결정

- Custom Domain 과 인증서
- EKS Version, Node Volume Size
- Gateway/HTTPRoute Listener 프로토콜
- EFS 성능·Lifecycle 세부
- RDS Minor Version
- Redis Cluster Mode / Multi-AZ
- 로그 보존 정책
- WAF Managed Rule / Rate Limit

---

## 16. 단계별 구축 및 검증 원칙

```text
00-bootstrap
→ 10-network 최소 기반
→ 20-security 최소 SG/IAM
→ 40-platform Bastion 우선 배포
→ 30-data
→ eksctl EKS (privateCluster, skipEndpointCreation)
→ helm ArgoCD 1회 + root-app
→ ArgoCD: ESO, Gateway API CRD, AWS LB Controller
→ Kubernetes Gateway/HTTPRoute/Service
→ AWS LB Controller 가 Private ALB/Target Group/Listener 생성
→ 40-platform CloudFront VPC Origin, CDN, WAF Association 최종 배포
```

**마지막 단계가 Gateway 에 의존한다.** CloudFront Origin 에 ALB 가 필요한데 그것은
Gateway 가 만든다. 한 번에 `terraform apply` 하면 실패한다.

각 단계에서 다음 절차를 반복한다.

```bash
terraform fmt -recursive
terraform validate
terraform plan -out=<단계명>.tfplan
terraform show -no-color <단계명>.tfplan
terraform apply <단계명>.tfplan
terraform plan
```

마지막 `terraform plan` 은 `No changes` 여야 한다. `-target` 을 반복 사용하지 않고
Root Module 에 Child Module 을 하나씩 추가하는 방식으로 진행한다.

---

## 17. 최종 문서에 단계마다 남길 근거

각 모듈별로 다음을 기록한다.

1. 구축 목적
2. 해당 모듈에 포함한 이유
3. 의존하는 모듈과 Output
4. 선택한 설정과 근거
5. 보안 고려사항
6. 비용 고려사항
7. Terraform Plan 결과
8. Apply 결과
9. AWS Console/CLI 검증 결과
10. 발생한 오류와 해결 방법
11. 현재 제약과 향후 개선점

---

## 18. 배포 전 확인 체크리스트

- [ ] 앱 워크플로에 `kubectl` / `kubeconfig` / `configure-aws-credentials` 가 없다
- [ ] 인프라 워크플로에 `docker` / 레지스트리 로그인이 없다
- [ ] 인프라 apply 가 깨진 상태에서 앱 빌드가 정상적으로 돈다
- [ ] 두 워크플로가 dispatch 로 서로를 트리거하지 않는다
- [ ] GitHub Secrets 에 장수명 클라우드 액세스 키가 0개다
- [ ] Private App Subnet 에 `kubernetes.io/role/internal-elb` 태그가 붙어 있다
- [ ] 적재 Job 과 런타임 파드가 **같은 ConfigMap** 을 본다
- [ ] `latest` 태그를 참조하는 매니페스트가 없다
- [ ] StorageClass 가 붙이는 태그와 AWS Backup selection 조건이 같다
- [ ] `/storage/*` HTTPRoute 가 있다 — 없으면 X-ray 히트맵이 안 뜬다
- [ ] **복원을 한 번 해 봤다** — 백업 계획이 초록인 것과 복원되는 것은 다르다
