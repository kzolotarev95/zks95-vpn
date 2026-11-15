# Мониторинг — запланирован

Prometheus, Grafana и Loki будут добавлены с метриками API, очередей и heartbeat нод. Сейчас контроль доступности осуществляется readiness/liveness API и Docker healthchecks. Пустые контейнеры мониторинга не запускаются.
