FROM node:22-slim AS deps

WORKDIR /app
COPY package*.json ./
RUN npm install

FROM node:22-slim AS build

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/package.json ./
COPY . .

# **빌드 인자를 두지 않는다.** 이 이미지는 AWS·GCP(DR)·로컬 어디서든 같은 것이다.
#
# 예전에는 두 개가 있었다. `NEXT_PUBLIC_API_BASE_URL` 은 API 주소를,
# `NEXT_PUBLIC_AI_FEATURES_ENABLED` 는 DR 여부를 받았다. `NEXT_PUBLIC_` 값은
# 번들에 박혀 기동 환경변수로 바뀌지 않으므로, 값이 다른 만큼 이미지가 갈라졌다 —
# 도메인마다 하나, DR 용으로 또 하나.
#
# 둘 다 없앴다. API 주소는 상대 경로로(services/http/client.ts), DR 여부는 서버가
# 낸 503 문구로 대체했다(config/AiFeatures.java). 이제 갈래가 하나다.
RUN npm run build

FROM node:22-slim AS runner

WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public

EXPOSE 3000
CMD ["npm", "run", "start", "--", "-p", "3000"]
