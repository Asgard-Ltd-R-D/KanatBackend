# ---- build ----
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

# Copy project files
COPY PacketProcessing.csproj ./
COPY src/ ./src/
COPY appsettings*.json ./

# Restore dependencies
RUN dotnet restore PacketProcessing.csproj

# Publish the application
RUN dotnet publish PacketProcessing.csproj -c Release -o /app

# ---- runtime ----
FROM mcr.microsoft.com/dotnet/aspnet:8.0

# Install required packages for packet capture
# libpcap for direct packet capture, tcpdump for debugging, net-tools for network utilities

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpcap0.8 \
    wireshark-common \
    tcpdump \
    net-tools \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy published application
COPY --from=build /app ./

# Set environment variables for .NET optimization
ENV DOTNET_GCServer=1
ENV DOTNET_RUNNING_IN_CONTAINER=true

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

ENTRYPOINT ["dotnet", "PacketProcessing.dll"]
