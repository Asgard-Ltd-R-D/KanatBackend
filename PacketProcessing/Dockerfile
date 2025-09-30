# Base runtime image
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS base
WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Build image
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

# Copy the project file and restore as distinct layers
COPY ["PacketProcessing.csproj", "./"]
RUN dotnet restore "PacketProcessing.csproj"

# Copy all source code
COPY . .

# Build the project
RUN dotnet build "PacketProcessing.csproj" -c Release -o /app/build

# Publish the application
FROM build AS publish
RUN dotnet publish "PacketProcessing.csproj" -c Release -o /app/publish /p:UseAppHost=true

# Final runtime image
FROM base AS final
WORKDIR /app
COPY --from=publish /app/publish .
COPY appsettings*.json ./
ENTRYPOINT ["dotnet", "PacketProcessing.dll"]