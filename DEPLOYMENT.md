# Complete NomiSafe Backend Deployment Guide for EC2

## Prerequisites Checklist

- ✅ EC2 instance running Ubuntu (20.04/22.04/24.04)
- ✅ Security group allows inbound on ports: 22 (SSH), 80 (HTTP), 443 (HTTPS optional)
- ✅ SSH key pair (`nomisafe-key.pem`) with proper permissions
- ✅ PostgreSQL installed and configured on EC2 (already done)

---

## Step 1: Prepare Local Environment

### 1.1 Make entrypoint.sh executable

```bash
cd /Users/avinash/dev/Projects/Nomisafe/NomiSafe-App/nomisafe-backend
chmod +x entrypoint.sh
```

### 1.2 Create production .env file

Create `.env` file in the backend directory with these variables:

```bash
cat > .env << 'EOF'
# Django Core
DJANGO_SECRET_KEY=your-very-long-random-secret-key-here-change-this
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=<YOUR_EC2_PUBLIC_IP>,<YOUR_DOMAIN>
DJANGO_CSRF_TRUSTED_ORIGINS=http://<YOUR_EC2_PUBLIC_IP>,https://<YOUR_DOMAIN>

# Database
POSTGRES_DB=nomisafe_db
POSTGRES_USER=nomisafe
POSTGRES_PASSWORD=NomiSafe2024SecurePass
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Optional: External Services
GEMINI_API_KEY=your-gemini-key-if-any
DIGILOCKER_CLIENT_ID=your-client-id
DIGILOCKER_CLIENT_SECRET=your-client-secret
DIGILOCKER_REDIRECT_URI=http://<YOUR_EC2_PUBLIC_IP>/api/aadhaar/digilocker/callback

# Twilio (if using SMS)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=

# Gunicorn
GUNICORN_WORKERS=3
EOF
```

**Important**: Replace `<YOUR_EC2_PUBLIC_IP>` and `<YOUR_DOMAIN>` with actual values.

### 1.3 Commit and push changes (optional but recommended)

```bash
cd /Users/avinash/dev/Projects/Nomisafe/NomiSafe-App/nomisafe-backend
git add .
git commit -m "Add Docker configuration for production deployment"
git push origin main
```

---

## Step 2: Transfer Code to EC2

### Option A: Using Git (Recommended)

```bash
# SSH into EC2
ssh -i ~/Desktop/nomisafe-key.pem ubuntu@<YOUR_EC2_PUBLIC_IP>

# Install git if not present
sudo apt update
sudo apt install -y git

# Clone repository
cd ~
git clone https://github.com/AvinashNomisafe/NomiSafe-backend.git nomisafe-backend
cd nomisafe-backend

# Or if already cloned, pull latest
cd ~/nomisafe-backend
git pull origin main
```

### Option B: Using SCP (Direct Transfer)

From your **local machine**:

```bash
cd /Users/avinash/dev/Projects/Nomisafe/NomiSafe-App

# Transfer entire backend directory
scp -i ~/Desktop/nomisafe-key.pem -r nomisafe-backend ubuntu@<YOUR_EC2_PUBLIC_IP>:~/
```

---

## Step 3: Install Docker on EC2

SSH into your EC2 instance:

```bash
ssh -i ~/Desktop/nomisafe-key.pem ubuntu@<YOUR_EC2_PUBLIC_IP>
```

### 3.1 Install Docker

```bash
# Update packages
sudo apt update
sudo apt install -y ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Set up Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Verify installation
sudo docker --version
sudo docker compose version
```

### 3.2 Add ubuntu user to docker group (avoid using sudo)

```bash
sudo usermod -aG docker ubuntu
newgrp docker

# Test without sudo
docker ps
```

---

## Step 4: Configure Environment on EC2

### 4.1 Navigate to backend directory

```bash
cd ~/nomisafe-backend
```

### 4.2 Create production .env file

```bash
nano .env
```

Paste the same content from Step 1.2, with correct EC2 IP:

```env
DJANGO_SECRET_KEY=your-very-long-random-secret-key-here-change-this
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=<YOUR_EC2_PUBLIC_IP>
DJANGO_CSRF_TRUSTED_ORIGINS=http://<YOUR_EC2_PUBLIC_IP>

POSTGRES_DB=nomisafe_db
POSTGRES_USER=nomisafe
POSTGRES_PASSWORD=NomiSafe2024SecurePass
POSTGRES_HOST=db
POSTGRES_PORT=5432

GUNICORN_WORKERS=3
```

Save with `Ctrl+O`, `Enter`, then `Ctrl+X`.

### 4.3 Make entrypoint executable

```bash
chmod +x entrypoint.sh
```

---

## Step 5: Configure PostgreSQL Connection

### Option A: Use Docker PostgreSQL (Recommended - Fresh Start)

The `docker-compose.yml` already includes PostgreSQL. Skip to Step 6.

### Option B: Use Host PostgreSQL (Already Configured)

If you want to use the PostgreSQL you already set up on EC2:

#### 5.1 Stop host PostgreSQL or change port

```bash
# Option 1: Stop host postgres to free port 5432 for docker
sudo systemctl stop postgresql
sudo systemctl disable postgresql

# Option 2: Keep it running, update docker-compose.yml to expose different port
```

#### 5.2 Modify docker-compose.yml to use host database

```bash
nano docker-compose.yml
```

Comment out the `db` service and update web service:

```yaml
version: "3.9"
services:
  # db:
  #   image: postgres:16
  #   ...

  web:
    build: .
    restart: unless-stopped
    env_file: .env
    # Remove depends_on: db
    command: /bin/sh /app/entrypoint.sh
    volumes:
      - media:/app/media
      - static:/app/staticfiles
    networks:
      - backend
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

Update `.env`:

```env
POSTGRES_HOST=172.17.0.1  # Docker bridge IP to reach host
# or
POSTGRES_HOST=host.docker.internal
```

**For this guide, we'll use Docker PostgreSQL (Option A)**.

---

## Step 6: Build and Deploy

### 6.1 Build Docker images

```bash
cd ~/nomisafe-backend
docker compose build --no-cache
```

This will take 3-5 minutes.

### 6.2 Start all services

```bash
docker compose up -d
```

### 6.3 Check container status

```bash
docker compose ps
```

You should see 3 containers running:

- `nomisafe-backend-db-1`
- `nomisafe-backend-web-1`
- `nomisafe-backend-nginx-1`

### 6.4 View logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f web
docker compose logs -f nginx
docker compose logs -f db
```

Watch for:

- ✅ "Database ready"
- ✅ "Operations to perform: X migrations"
- ✅ "X static files copied"
- ✅ "Booting Gunicorn with X workers"

Press `Ctrl+C` to exit logs.

---

## Step 7: Verify Deployment

### 7.1 Check from EC2

```bash
# Test nginx is responding
curl -I http://localhost

# Test API endpoint
curl http://localhost/api/send-otp/ -X POST \
  -H "Content-Type: application/json" \
  -d '{"phone": "+919876543210"}'
```

### 7.2 Check from your local machine

```bash
# From your Mac
curl -I http://<YOUR_EC2_PUBLIC_IP>
```

### 7.3 Open in browser

Visit: `http://<YOUR_EC2_PUBLIC_IP>/admin/`

You should see the Django admin login page.

---

## Step 8: Create Django Superuser

```bash
docker compose exec web python manage.py createsuperuser
```

Enter:

- Username: `admin`
- Email: your email
- Password: (strong password)

Test login at: `http://<YOUR_EC2_PUBLIC_IP>/admin/`

---

## Step 9: Database Migration (If Using Existing Data)

### 9.1 Backup existing host database

```bash
sudo -u postgres pg_dump nomisafe_db > ~/backup_$(date +%F).sql
```

### 9.2 Restore to Docker PostgreSQL

```bash
# Copy backup into container
docker cp ~/backup_2025-11-25.sql nomisafe-backend-db-1:/tmp/backup.sql

# Restore
docker compose exec db psql -U nomisafe -d nomisafe_db -f /tmp/backup.sql
```

---

## Step 10: Enable Services on Boot

### 10.1 Install Docker Compose systemd service

```bash
sudo nano /etc/systemd/system/nomisafe-backend.service
```

Paste:

```ini
[Unit]
Description=NomiSafe Backend Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/ubuntu/nomisafe-backend
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

### 10.2 Enable and start service

```bash
sudo systemctl daemon-reload
sudo systemctl enable nomisafe-backend.service
sudo systemctl start nomisafe-backend.service

# Check status
sudo systemctl status nomisafe-backend.service
```

Now containers will auto-start on EC2 reboot.

---

## Step 11: Testing & Troubleshooting

### Common Commands

```bash
# Restart all services
docker compose restart

# Restart specific service
docker compose restart web

# View logs
docker compose logs -f web

# Execute Django commands
docker compose exec web python manage.py migrate
docker compose exec web python manage.py shell
docker compose exec web python manage.py collectstatic --noinput

# Access PostgreSQL
docker compose exec db psql -U nomisafe -d nomisafe_db

# Check running containers
docker ps

# Remove all and rebuild
docker compose down -v
docker compose up -d --build
```

### Debugging Issues

#### Port 80 already in use

```bash
# Check what's using port 80
sudo lsof -i :80
sudo systemctl stop apache2  # if Apache is running
```

#### Database connection errors

```bash
# Check if db container is running
docker compose ps

# Check db logs
docker compose logs db

# Manually test connection
docker compose exec web python manage.py dbshell
```

#### Static files not loading

```bash
# Re-collect static files
docker compose exec web python manage.py collectstatic --noinput

# Check nginx config
docker compose exec nginx cat /etc/nginx/conf.d/default.conf

# Check static volume
docker compose exec nginx ls -la /app/staticfiles/
```

---

## Step 12: Security Hardening (Production)

### 12.1 Update security group

- Allow only specific IPs for SSH (port 22)
- Keep port 80/443 open to 0.0.0.0/0
- Block all other ports

### 12.2 Set up HTTPS with Let's Encrypt (Optional)

Install Certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx

# Stop nginx container temporarily
docker compose stop nginx

# Get certificate
sudo certbot certonly --standalone -d your-domain.com

# Copy certificates into nginx volume
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ~/nomisafe-backend/ssl/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem ~/nomisafe-backend/ssl/
```

Update `nginx.conf` to include SSL configuration.

### 12.3 Enable firewall

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## Step 13: Monitoring & Maintenance

### View resource usage

```bash
docker stats
```

### Backup database regularly

```bash
# Create backup script
cat > ~/backup-db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=/home/ubuntu/backups
mkdir -p $BACKUP_DIR
docker compose -f /home/ubuntu/nomisafe-backend/docker-compose.yml exec -T db \
  pg_dump -U nomisafe nomisafe_db > $BACKUP_DIR/backup_$(date +\%F_\%H\%M).sql
# Keep only last 7 days
find $BACKUP_DIR -name "backup_*.sql" -mtime +7 -delete
EOF

chmod +x ~/backup-db.sh

# Add to crontab (daily at 2 AM)
(crontab -l 2>/dev/null; echo "0 2 * * * /home/ubuntu/backup-db.sh") | crontab -
```

---

## Step 14: Update & Redeploy

When you make code changes:

### From local machine:

```bash
cd /Users/avinash/dev/Projects/Nomisafe/NomiSafe-App/nomisafe-backend
git add .
git commit -m "Your changes"
git push origin main
```

### On EC2:

```bash
cd ~/nomisafe-backend
git pull origin main
docker compose build
docker compose up -d --force-recreate web
docker compose logs -f web
```

---

## Quick Reference

### Service URLs

- Main API: `http://<EC2_IP>/api/`
- Admin Panel: `http://<EC2_IP>/admin/`
- Static Files: `http://<EC2_IP>/static/`
- Media Files: `http://<EC2_IP>/media/`

### Important Paths on EC2

- Project: `~/nomisafe-backend/`
- Logs: `docker compose logs`
- Database Volume: Docker managed
- Media Files: Docker volume `nomisafe-backend_media`
- Static Files: Docker volume `nomisafe-backend_static`

### Common Tasks

| Task             | Command                                                    |
| ---------------- | ---------------------------------------------------------- |
| Start services   | `docker compose up -d`                                     |
| Stop services    | `docker compose down`                                      |
| View logs        | `docker compose logs -f`                                   |
| Restart          | `docker compose restart`                                   |
| Run migrations   | `docker compose exec web python manage.py migrate`         |
| Create superuser | `docker compose exec web python manage.py createsuperuser` |
| Django shell     | `docker compose exec web python manage.py shell`           |
| Database shell   | `docker compose exec db psql -U nomisafe -d nomisafe_db`   |

---

## Support

If you encounter issues:

1. Check logs: `docker compose logs -f`
2. Verify .env file has correct values
3. Ensure security group allows port 80
4. Check container status: `docker compose ps`
5. Verify disk space: `df -h`

---

**Deployment Complete! 🚀**

Your NomiSafe backend is now running in production on EC2 with Docker.
