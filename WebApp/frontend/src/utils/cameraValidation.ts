import { CameraInput } from '../types'

// The backend enforces the same rules (backend/app/schemas/camera.py): these
// values end up in the command that starts the camera's GStreamer

// What the form edits: every field as typed
export interface CameraForm {
  alias: string
  mcast_ip: string
  mcast_port: string
  iface: string
  enabled: boolean
}

export type CameraFormErrors = Partial<Record<keyof CameraForm, string>>

const ALIAS = /^[A-Za-z0-9][A-Za-z0-9_-]{1,62}$/
const IPV4 = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/
// Multicast groups are 224.0.0.0 to 239.255.255.255
const isMulticast = (ip: string) => IPV4.test(ip) && Number(ip.split('.')[0]) >= 224 && Number(ip.split('.')[0]) <= 239
const IFACE = /^[A-Za-z0-9._:-]{1,32}$/

export const EMPTY_CAMERA_FORM: CameraForm = { alias: '', mcast_ip: '', mcast_port: '', iface: '', enabled: true }

export function toForm(camera: CameraInput): CameraForm {
  return {
    alias: camera.alias,
    mcast_ip: camera.mcast_ip,
    mcast_port: String(camera.mcast_port),
    iface: camera.iface ?? '',
    enabled: camera.enabled,
  }
}

export function validateCamera(form: CameraForm): CameraFormErrors {
  const errors: CameraFormErrors = {}
  const alias = form.alias.trim()
  const port = Number(form.mcast_port)

  if (!ALIAS.test(alias)) {
    errors.alias = '2–63 characters: letters, digits, - and _, starting with a letter or digit'
  }
  if (!isMulticast(form.mcast_ip.trim())) {
    errors.mcast_ip = 'A multicast group (224.0.0.0 – 239.255.255.255), e.g. 226.226.226.112'
  }
  if (!form.mcast_port.trim() || !Number.isInteger(port) || port < 1 || port > 65535) {
    errors.mcast_port = 'A port from 1 to 65535'
  }
  if (form.iface.trim() && !IFACE.test(form.iface.trim())) {
    errors.iface = 'An interface name, e.g. eth1 or enp2s0'
  }
  return errors
}

export function toInput(form: CameraForm): CameraInput {
  return {
    alias: form.alias.trim(),
    mcast_ip: form.mcast_ip.trim(),
    mcast_port: Number(form.mcast_port),
    iface: form.iface.trim() || null,
    enabled: form.enabled,
  }
}
