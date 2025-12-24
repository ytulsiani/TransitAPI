package com.mbta.mbtaapi;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class LineResponse {
    public List<LineData> data;

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class LineData {
        public String id;
        public LineAttributes attributes;
        public LineRelationships relationships;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class LineAttributes {
        @JsonProperty("long_name")
        public String longName;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class LineRelationships {
        public RouteCollection routes;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class RouteCollection {
        public List<RouteRef> data;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class RouteRef {
        public String id;
    }
}
