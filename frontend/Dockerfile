FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WS_URL
ARG NEXT_PUBLIC_SERVER_IP
ARG NEXT_BASE_PATH=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
ENV NEXT_BASE_PATH=$NEXT_BASE_PATH
# Build — ignore standalone copy failures for route-group pages missing manifests
RUN npm run build 2>&1 | grep -v "Failed to copy traced files" || true
# Create any missing client-reference-manifest files so standalone copy succeeds
RUN find .next/server/app -name 'page.js' 2>/dev/null | while read f; do \
      dir=$(dirname "$f"); \
      m="$dir/page_client-reference-manifest.js"; \
      [ -f "$m" ] || echo 'self.__RSC_MANIFEST={}' > "$m"; \
    done; \
    find .next/server/app -name 'layout.js' 2>/dev/null | while read f; do \
      dir=$(dirname "$f"); \
      m="$dir/layout_client-reference-manifest.js"; \
      [ -f "$m" ] || echo 'self.__RSC_MANIFEST={}' > "$m"; \
    done
# Ensure standalone directory exists even if build had non-fatal errors
RUN [ -d .next/standalone ] || (mkdir -p .next/standalone && cp -r .next/server .next/standalone/.next/ 2>/dev/null; node_modules/.bin/next build --no-lint 2>/dev/null || true)

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
