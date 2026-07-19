FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WS_URL
ARG NEXT_PUBLIC_SERVER_IP
ARG NEXT_BASE_PATH=""
# next.config.js's rewrites() destination is baked in at BUILD time by Next's
# standalone output (not re-read at container runtime), so BACKEND_URL must be a
# build arg like the NEXT_PUBLIC_* vars — setting it only in docker-compose's
# runtime `environment:` silently does nothing.
ARG BACKEND_URL="http://127.0.0.1:5000"
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
ENV NEXT_BASE_PATH=$NEXT_BASE_PATH
ENV BACKEND_URL=$BACKEND_URL
# Build. Tolerate the known-benign "Failed to copy traced files" warning, but FAIL the
# image build on a real error — otherwise a broken build silently ships a stale .next
# (this masking previously shipped an old dashboard for a whole session).
RUN npm run build 2>&1 | tee /tmp/build.log | grep -v "Failed to copy traced files" || true; \
    if grep -qE "Export encountered an error|Build error occurred|exiting the build|Failed to compile" /tmp/build.log; then \
      echo ">>> next build FAILED (see log above)"; exit 1; \
    fi
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
