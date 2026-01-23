#
# Dockerfile - nginx for Leafy Media (Kanopy)
# Main container serving static files and proxying to Flask sidecar
#

FROM nginx:alpine

# Copy nginx configuration
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# Copy templates assets (matches Ben's original directory structure)
# All static files served from /app/templates/
COPY app/templates/css /app/templates/css
COPY app/templates/js /app/templates/js
COPY app/templates/img /app/templates/img
COPY app/templates/fontawesome /app/templates/fontawesome
COPY app/templates/video /app/templates/video

# Kanopy requires port 8080
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
