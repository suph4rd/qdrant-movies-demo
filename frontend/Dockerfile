FROM node:24.22.2-bookworm-slim AS client
WORKDIR /client
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM nginx:1.28.2-alpine@sha256:5b4900b042ccfa8b0a73df622c3a60f2322faeb2be800cbee5aa7b44d241649e
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=client /client/dist /usr/share/nginx/html
EXPOSE 80
