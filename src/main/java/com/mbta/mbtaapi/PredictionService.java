package com.mbta.mbtaapi;

import java.io.IOException;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class PredictionService {
    private final MbtaClient mbtaClient;

    public PredictionService(MbtaClient mbtaClient) {
        this.mbtaClient = mbtaClient;
    }

    public List<PredictionSummary> getPredictions(PredictionRequest request)
            throws IOException, InterruptedException {
        if (request == null || request.stopId == null || request.stopId.isBlank()) {
            throw new IllegalArgumentException("stopId must not be blank");
        }
        PredictionRequest normalized = normalizeRequest(request);
        List<PredictionSummary> raw = mbtaClient.fetchPredictions(normalized);
        return raw.stream()
                .sorted(
                        Comparator.comparing(
                                ps -> ps.arrivalTime, Comparator.nullsLast(Comparator.naturalOrder())))
                .toList();
    }

    private PredictionRequest normalizeRequest(PredictionRequest request) {
        PredictionRequest normalized = new PredictionRequest();
        normalized.stopId = request.stopId;
        normalized.direction = request.direction;
        normalized.limit = (request.limit == null || request.limit <= 0) ? 2 : request.limit;
        normalized.routes =
                request.routes == null
                        ? null
                        : request.routes.stream()
                                .filter(Objects::nonNull)
                                .filter(r -> !r.isBlank())
                                .collect(Collectors.toSet());
        return normalized;
    }
}
