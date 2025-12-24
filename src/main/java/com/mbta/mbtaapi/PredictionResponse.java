package com.mbta.mbtaapi;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class PredictionResponse {
    public List<PredictionData> data;
    public List<Included> included;

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class PredictionData {
        public PredictionAttributes attributes;
        public PredictionRelationships relationships;

        public String routeId() {
            if (relationships == null || relationships.route == null || relationships.route.data == null) {
                return null;
            }
            return relationships.route.data.id;
        }

        public String tripId() {
            if (relationships == null || relationships.trip == null || relationships.trip.data == null) {
                return null;
            }
            return relationships.trip.data.id;
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class PredictionAttributes {
        public String headsign;

        @JsonProperty("arrival_time")
        public String arrivalTime;

        @JsonProperty("arrival_uncertainty")
        public Integer arrivalUncertainty;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class PredictionRelationships {
        public RouteRelationship route;
        public TripRelationship trip;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class RouteRelationship {
        public RouteRef data;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class RouteRef {
        public String id;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class TripRelationship {
        public TripRef data;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class TripRef {
        public String id;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Included {
        public String id;
        public String type;
        public TripAttributes attributes;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class TripAttributes {
        public String headsign;
    }
}
