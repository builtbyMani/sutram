FROM node:22-alpine

WORKDIR /srv/web

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Production build: the demo must not depend on next dev's on-demand
# compilation (slow first paint, recompiles mid-demo). next.config.ts reads
# API_URL at server start for its rewrite proxy, so no build-time API URL
# is needed here; compose sets API_URL=http://api:8000 at runtime.
RUN npm run build

ENV API_URL=http://localhost:8000
EXPOSE 3000

CMD ["npm", "run", "start", "--", "--port", "3000", "--hostname", "0.0.0.0"]
