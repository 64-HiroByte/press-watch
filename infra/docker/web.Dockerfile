FROM node:24-bookworm-slim

WORKDIR /workspace

ENV NEXT_TELEMETRY_DISABLED=1

RUN npm install -g pnpm@10.0.0

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json

RUN pnpm install --filter @press-watch/web... --frozen-lockfile

COPY apps/web apps/web

EXPOSE 3000

CMD ["pnpm", "--filter", "@press-watch/web", "dev", "--hostname", "0.0.0.0"]
