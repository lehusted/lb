FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:15c994d10d6d78658721c3bcafff14cb281fba2a4bdf9d5ba92c416a472516e3
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html styles.css app.js monitorering.html monitorering.js /usr/share/nginx/html/
EXPOSE 8080
