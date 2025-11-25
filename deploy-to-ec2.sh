#!/bin/bash
set -e

EC2_IP="51.20.84.242"
KEY_PATH="~/Desktop/nomisafe-key.pem"
LOCAL_DIR="/Users/avinash/dev/Projects/Nomisafe/NomiSafe-App/nomisafe-backend"

echo "🚀 Starting deployment to EC2..."

# Step 1: Commit and push changes (if any)
echo "📦 Pushing latest changes to git..."
cd $LOCAL_DIR
if [[ -n $(git status -s) ]]; then
    echo "Uncommitted changes found. Please commit and push first."
    exit 1
fi

# Step 2: Install Docker and deploy
echo "🐳 Installing Docker and deploying application..."
ssh -i $KEY_PATH ubuntu@$EC2_IP << 'ENDSSH'
set -e

# Clone or pull repository
if [ ! -d "nomisafe-backend" ]; then
    echo "📥 Cloning repository..."
    git clone https://github.com/AvinashNomisafe/NomiSafe-backend.git nomisafe-backend
else
    echo "📥 Pulling latest changes..."
    cd nomisafe-backend
    git pull origin main
    cd ~
fi

# Update system
sudo apt update

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    
    # Install dependencies
    sudo apt install -y ca-certificates curl gnupg lsb-release
    
    # Add Docker GPG key
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    
    # Add Docker repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Install Docker
    sudo apt update
    sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Add user to docker group
    sudo usermod -aG docker ubuntu
    echo "✅ Docker installed successfully"
else
    echo "✅ Docker already installed"
fi

# Navigate to project
cd ~/nomisafe-backend

# Make entrypoint executable
chmod +x entrypoint.sh

# Stop host PostgreSQL if running (to free port 5432)
if sudo systemctl is-active --quiet postgresql; then
    echo "Stopping host PostgreSQL..."
    sudo systemctl stop postgresql
    sudo systemctl disable postgresql
fi

# Build and start containers
echo "🏗️  Building Docker images..."
docker compose build --no-cache

echo "🚀 Starting containers..."
docker compose up -d

echo "⏳ Waiting for services to start..."
sleep 10

# Show status
docker compose ps

echo ""
echo "📋 Viewing logs..."
docker compose logs --tail=50

echo ""
echo "✅ Deployment complete!"
echo ""
echo "🌐 Your backend is now available at:"
echo "   - API: http://51.20.84.242/api/"
echo "   - Admin: http://51.20.84.242/admin/"
echo ""
echo "📝 Next steps:"
echo "   1. Create superuser: docker compose exec web python manage.py createsuperuser"
echo "   2. View logs: docker compose logs -f"
echo "   3. Restart: docker compose restart"
echo ""
ENDSSH

echo ""
echo "✨ All done! Check the output above for any errors."
