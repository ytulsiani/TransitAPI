package com.mbta.mbtaapi;

public class PredictionSummary {
    public String headsign;
    public Long arrivalTime;
    public Integer arrivalUncertainty;

    public PredictionSummary() {}

    public PredictionSummary(String headsign, Long arrivalTime, Integer arrivalUncertainty) {
        this.headsign = headsign;
        this.arrivalTime = arrivalTime;
        this.arrivalUncertainty = arrivalUncertainty;
    }

    public static PredictionSummary fromPredictionData(PredictionResponse.PredictionData data) {
        if (data == null || data.attributes == null) {
            return new PredictionSummary();
        }

        PredictionResponse.PredictionAttributes attr = data.attributes;
        String headsign = attr.headsign != null ? attr.headsign : data.routeId();
        Long arrivalEpoch = null;
        if (attr.arrivalTime != null && !attr.arrivalTime.isBlank()) {
            try {
                arrivalEpoch = java.time.Instant.parse(attr.arrivalTime).getEpochSecond();
            } catch (java.time.format.DateTimeParseException e) {
                arrivalEpoch = null;
            }
        }
        return new PredictionSummary(headsign, arrivalEpoch, attr.arrivalUncertainty);
    }
}
