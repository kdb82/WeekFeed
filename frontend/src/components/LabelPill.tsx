import { LABEL_NAMES, type Label } from '../types'
import styles from './LabelPill.module.css'

export default function LabelPill({ label }: { label: Label }) {
  return <span className={`${styles.pill} ${styles[label]}`}>{LABEL_NAMES[label]}</span>
}
