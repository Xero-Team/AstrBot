# Deploy AstrBot with Kubernetes

> [!WARNING]
> You can deploy AstrBot in a high-availability setup using Kubernetes (K8s), allowing it to automatically recover from failures.
>
> Due to the current use of an SQLite database, this deployment does not support horizontal scaling with multiple replicas. Additionally, if using the Sidecar mode, pay special attention to the persistence of NapCat's login state.
>
> The following tutorial assumes that you have `kubectl` installed and configured, and that you can connect to your K8s cluster.

## Prerequisites

Before you begin, make sure your Kubernetes cluster meets the following conditions:

1. **Default StorageClass**: Used to dynamically create `PersistentVolumeClaim` (PVC). You can check this with `kubectl get sc`. If you don't have one, you need to manually create a `PersistentVolume` (PV) or install a corresponding storage plugin (e.g., `nfs-client-provisioner`).
2. **Network Access**: Ensure that your cluster nodes can pull the AstrBot image from your chosen registry, plus dependency images such as NapCat and BusyBox.

## Deployment Methods

We offer two deployment options:

- **Integrated Deployment (Sidecar Mode)**: Deploy AstrBot and NapCat in the same Pod. Recommended for personal QQ accounts.
- **Standalone Deployment**: Deploy only AstrBot. Suitable for other platforms or if you want to manage NapCat independently.

---

### Method 1: Deploy with NapCatQQ (Sidecar)

This method is located in the `k8s/astrbot_with_napcat` directory.

#### 1. Deploy

```bash
# 1. Create namespace
kubectl apply -f k8s/astrbot_with_napcat/00-namespace.yaml

# 2. Create Persistent Volume Claim
# Note: astrbot-data-shared-pvc requires ReadWriteMany (RWX) access mode.
# If your cluster does not support RWX, you need to configure shared storage such as NFS and modify the storageClassName in 01-pvc.yaml.
kubectl apply -f k8s/astrbot_with_napcat/01-pvc.yaml

# 3. Deploy the application
kubectl apply -f k8s/astrbot_with_napcat/02-deployment.yaml
```

#### 2. Expose Service (Choose one)

- **Option A: NodePort**

  ```bash
  kubectl apply -f k8s/astrbot_with_napcat/03-service-nodeport.yaml
  ```

  The service will be exposed via the node IP and a port automatically assigned by Kubernetes. You can find the port with the following command:

  ```bash
  kubectl get svc -n astrbot-ns
  ```

  In the output, find the `PORT(S)` column for `astrbot-webui-svc` and `napcat-web-svc`. The format is `<internal-port>:<NodePort>/TCP`. For example, if you see `8080:30185/TCP`, the access address is `http://<NodeIP>:30185`.

- **Option B: LoadBalancer**

  If your cluster supports `LoadBalancer` type services (usually provided in K8s services from cloud providers), you can use this method.

  ```bash
  kubectl apply -f k8s/astrbot_with_napcat/04-service-loadbalancer.yaml
  ```

  After execution, check the assigned external IP (EXTERNAL-IP) with `kubectl get svc -n astrbot-ns`.

#### 3. Configure Connection

Since AstrBot and NapCat are in the same Pod, they can communicate directly via `localhost`.

1. **Add a message platform in AstrBot:**
   - Go to the AstrBot WebUI, select `Platform` -> `Add`.
   - **Select Message Platform Category**: `napcat`
   - **Bot Name**: `napcat` (or custom)
   - **NapCat WebSocket URL**: `ws://localhost:3001`
   - **NapCat Token**: fill this only if NapCat enables WebSocket auth
   - Save the configuration.

2. **Make sure NapCat OneBot v11 forward WebSocket is enabled:**
   - The default example uses `ws://localhost:3001`
   - If a token is configured there, AstrBot must use the same token

---

### Method 2: Deploy AstrBot Only (General Purpose)

This method is located in the `k8s/astrbot` directory.

#### 1. Deploy

```bash
# 1. Create namespace
kubectl apply -f k8s/astrbot/00-namespace.yaml

# 2. Create Persistent Volume Claim
kubectl apply -f k8s/astrbot/01-pvc.yaml

# 3. Deploy the application
kubectl apply -f k8s/astrbot/02-deployment.yaml
```

#### 2. Expose Service (Choose one)

- **Option A: NodePort**

  ```bash
  kubectl apply -f k8s/astrbot/03-service-nodeport.yaml
  ```

  The service will be exposed via the node IP and a port automatically assigned by Kubernetes. You can find the port with the following command:

  ```bash
  kubectl get svc -n astrbot-standalone-ns
  ```

  In the output, find the `PORT(S)` column for `astrbot-webui-svc`. The format is `<internal-port>:<NodePort>/TCP`. For example, if you see `8080:30185/TCP`, the access address is `http://<NodeIP>:30185`.

- **Option B: LoadBalancer**

  ```bash
  kubectl apply -f k8s/astrbot/04-service-loadbalancer.yaml
  ```

  After execution, check the assigned external IP (EXTERNAL-IP) with `kubectl get svc -n astrbot-standalone-ns`.

---

## Advanced Configuration

### Prepare the AstrBot Image

This fork does not publish an official Kubernetes image. Before deploying to a cluster, build the AstrBot image yourself, push it to a registry you control, and then update the `image` field in the relevant `02-deployment.yaml`.

Example:

```bash
docker build -t <your-registry>/astrbot:<tag> .
docker push <your-registry>/astrbot:<tag>
```

Then replace the manifest value in `k8s/astrbot/02-deployment.yaml` or `k8s/astrbot_with_napcat/02-deployment.yaml` with:

```yaml
image: <your-registry>/astrbot:<tag>
```

If you also need a mirrored or self-hosted NapCat image, update that `image` field the same way.

### Sandbox Runtime

This repository's Kubernetes manifests do not ship a dedicated in-cluster sandbox runtime configuration.

If you need Agent sandbox / computer-use capabilities, follow the current [Agent Sandbox Environment](/en/use/astrbot-agent-sandbox.md) guide and deploy the chosen runtime separately. Do not rely on the removed legacy Docker code-interpreter workflow.

## View Logs

- **Sidecar Deployment Mode:**

  ```bash
  # View AstrBot logs
  kubectl logs -f -n astrbot-ns deployment/astrbot-stack -c astrbot

  # View NapCat logs
  kubectl logs -f -n astrbot-ns deployment/astrbot-stack -c napcat
  ```

- **Standalone Deployment Mode:**

  ```bash
  kubectl logs -f -n astrbot-standalone-ns deployment/astrbot-standalone
  ```

## 🎉 All Done

After deploying and exposing the service, you can access the AstrBot admin panel through the corresponding IP and port.

> New users must use the random password printed in the startup logs for the first login. Use the username shown in the logs (usually `astrbot`) and change it after logging in.
